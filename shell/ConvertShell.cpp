#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <shobjidl.h>
#include <shlwapi.h>
#include <shellapi.h>
#include <atomic>
#include <string>
#include <vector>
#include <new>
#include <memory>
#include <mutex>

// Same CLSID in AppxManifest.xml, install.ps1, and the COM verification harness.
const CLSID CLSID_Convert = {0x5e925d56,0x17c4,0x4cb1,{0x9c,0x91,0x70,0xb5,0xc5,0xb5,0x5e,0x62}};
HMODULE moduleHandle;
bool ukrainian() { return PRIMARYLANGID(GetUserDefaultUILanguage()) == LANG_UKRAINIAN; }
const wchar_t* convertLabel() { return ukrainian() ? L"Конвертувати" : L"Convert"; }
std::atomic<long> objects{0};
#include "Routes.generated.h"

std::wstring folder() {
    wchar_t path[32768]{};
    GetModuleFileNameW(moduleHandle, path, ARRAYSIZE(path));
    PathRemoveFileSpecW(path);
    return path;
}
std::wstring extension(const std::wstring& path) {
    std::wstring ext = PathFindExtensionW(path.c_str());
    for (auto& c : ext) c = towlower(c);
    std::wstring lowered = path;
    for (auto& c : lowered) c = towlower(c);
    for (auto& rule : inputRules) {
        std::wstring candidate(rule.extension);
        if (candidate.size() > ext.size() && lowered.size() >= candidate.size()
            && lowered.compare(lowered.size() - candidate.size(), candidate.size(), candidate) == 0)
            ext = candidate;
    }
    if (ext == L".jpeg" || ext == L".jpe" || ext == L".jfif") ext = L".jpg";
    if (ext == L".apng") ext = L".png";
    if (ext == L".dib") ext = L".bmp";
    if (ext == L".tif") ext = L".tiff";
    if (ext == L".heif") ext = L".heic";
    if (ext == L".htm") ext = L".html";
    if (ext == L".markdown") ext = L".md";
    return ext;
}
RouteMask targets(const std::wstring& ext) {
    for (auto& rule : inputRules) if (ext == rule.extension) return rule.mask;
    return {};
}
bool isOggVideo(const std::wstring& path) {
    HANDLE file=CreateFileW(path.c_str(),GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
    if(file==INVALID_HANDLE_VALUE)return false;
    std::string bytes(65536,'\0');DWORD count=0;
    bool ok=ReadFile(file,bytes.data(),static_cast<DWORD>(bytes.size()),&count,nullptr)!=0;
    CloseHandle(file);bytes.resize(count);
    return ok && bytes.compare(0,4,"OggS")==0 && (bytes.find("\x80theora")!=std::string::npos || bytes.find("BBCD")!=std::string::npos);
}
bool hasWinRAR() {
    for (const wchar_t* variable : {L"ProgramFiles", L"ProgramFiles(x86)"}) {
        wchar_t directory[32768]{};
        if (GetEnvironmentVariableW(variable, directory, ARRAYSIZE(directory))) {
            auto path = std::wstring(directory) + L"\\WinRAR\\Rar.exe";
            if (GetFileAttributesW(path.c_str()) != INVALID_FILE_ATTRIBUTES) return true;
        }
    }
    return false;
}
std::vector<std::wstring> paths(IShellItemArray* items) {
    std::vector<std::wstring> result;
    DWORD count = 0;
    if (!items || FAILED(items->GetCount(&count))) return result;
    for (DWORD i = 0; i < count; ++i) {
        IShellItem* item = nullptr;
        if (SUCCEEDED(items->GetItemAt(i, &item))) {
            PWSTR path = nullptr;
            if (SUCCEEDED(item->GetDisplayName(SIGDN_FILESYSPATH, &path))) {
                DWORD attributes = GetFileAttributesW(path);
                // ZIP/7Z can be shell namespace folders while remaining files.
                if (attributes != INVALID_FILE_ATTRIBUTES && !(attributes & FILE_ATTRIBUTE_DIRECTORY))
                    result.emplace_back(path);
                CoTaskMemFree(path);
            }
            item->Release();
        }
    }
    return result;
}

// Explorer can pass a null selection to deeper flyouts. Share the root selection
// with every child, rather than hiding working commands in nested menus.
struct Selection {
    std::mutex lock;
    std::vector<std::wstring> files;
    std::vector<std::wstring> get(IShellItemArray* items) {
        if (items) {
            auto current = paths(items);
            DWORD total = 0;
            if (FAILED(items->GetCount(&total)) || current.size() != total) current.clear();
            std::lock_guard<std::mutex> guard(lock);
            files = std::move(current);
            return files;
        }
        std::lock_guard<std::mutex> guard(lock);
        return files;
    }
};

class Command;
class Enumerator final : public IEnumExplorerCommand {
    std::atomic<ULONG> refs{1};
    ULONG position = 0;
    std::vector<int> nodes;
    std::shared_ptr<Selection> selection;
public:
    explicit Enumerator(std::shared_ptr<Selection> context) : selection(context) {
        ++objects;
        // Explorer supports one submenu level only. Never return category commands
        // containing another submenu: Windows renders those flyouts empty.
        for (int i = 0; i < ARRAYSIZE(outputRules); ++i) nodes.push_back(i);
    }
    ~Enumerator() { --objects; }
    IFACEMETHODIMP QueryInterface(REFIID iid, void** out) override {
        if (!out) return E_POINTER;
        *out = nullptr;
        if (iid == IID_IUnknown || iid == __uuidof(IEnumExplorerCommand)) {
            *out = static_cast<IEnumExplorerCommand*>(this); AddRef(); return S_OK;
        }
        return E_NOINTERFACE;
    }
    IFACEMETHODIMP_(ULONG) AddRef() override { return ++refs; }
    IFACEMETHODIMP_(ULONG) Release() override { ULONG n = --refs; if (!n) delete this; return n; }
    IFACEMETHODIMP Next(ULONG count, IExplorerCommand** commands, ULONG* fetched) override;
    IFACEMETHODIMP Skip(ULONG count) override {
        ULONG remaining = static_cast<ULONG>(nodes.size()) - position;
        position += count < remaining ? count : remaining;
        return count <= remaining ? S_OK : S_FALSE;
    }
    IFACEMETHODIMP Reset() override { position = 0; return S_OK; }
    IFACEMETHODIMP Clone(IEnumExplorerCommand** out) override {
        if (!out) return E_POINTER;
        auto copy = new(std::nothrow) Enumerator(selection);
        if (!copy) return E_OUTOFMEMORY;
        copy->position = position; *out = copy; return S_OK;
    }
};

class Command final : public IExplorerCommand {
    std::atomic<ULONG> refs{1};
    int format;
    std::shared_ptr<Selection> selection;
public:
    explicit Command(int index = -1, std::shared_ptr<Selection> context = nullptr) : format(index),
        selection(context ? context : std::make_shared<Selection>()) { ++objects; }
    ~Command() { --objects; }
    IFACEMETHODIMP QueryInterface(REFIID iid, void** out) override {
        if (!out) return E_POINTER;
        *out = nullptr;
        if (iid == IID_IUnknown || iid == __uuidof(IExplorerCommand)) {
            *out = static_cast<IExplorerCommand*>(this); AddRef(); return S_OK;
        }
        return E_NOINTERFACE;
    }
    IFACEMETHODIMP_(ULONG) AddRef() override { return ++refs; }
    IFACEMETHODIMP_(ULONG) Release() override { ULONG n = --refs; if (!n) delete this; return n; }
    IFACEMETHODIMP GetTitle(IShellItemArray* items, PWSTR* title) override {
        if (items) selection->get(items);
        if (format == -1) return SHStrDupW(convertLabel(), title);
        return SHStrDupW(outputRules[format].label, title);
    }
    IFACEMETHODIMP GetIcon(IShellItemArray*, PWSTR* icon) override {
        return SHStrDupW((folder() + L"\\ConvertIt.exe,0").c_str(), icon);
    }
    IFACEMETHODIMP GetToolTip(IShellItemArray*, PWSTR* tip) override {
        return SHStrDupW(format >= 0 ? outputRules[format].label : convertLabel(), tip);
    }
    IFACEMETHODIMP GetCanonicalName(GUID* name) override {
        if (!name) return E_POINTER;
        *name = CLSID_Convert;
        if (format >= 0) name->Data1 += format + 1;
        return S_OK;
    }
    IFACEMETHODIMP GetState(IShellItemArray* items, BOOL, EXPCMDSTATE* state) override {
        if (!state) return E_POINTER;
        *state = ECS_HIDDEN;
        auto selected = selection->get(items);
        if (selected.empty()) return S_OK;
        RouteMask common, inputFormats;
        common.set();
        for (auto& path : selected) {
            auto ext = extension(path);
            common &= targets(ext==L".ogg" && isOggVideo(path)?L".ogv":ext);
            for (int i = 0; i < ARRAYSIZE(outputRules); ++i)
                if (ext == std::wstring(L".") + outputRules[i].extension)
                    inputFormats.set(i);
        }
        // Offer only targets different from every selected input. This also
        // prevents partial same-format failures for mixed file selections.
        common &= ~inputFormats;
        for (int i = 0; i < ARRAYSIZE(outputRules); ++i)
            if (std::wstring(outputRules[i].id) == L"rar" && common.test(i) && !hasWinRAR()) common.reset(i);
        if (common.none()) return S_OK;
        if (format >= 0 && !common.test(format)) return S_OK;
        *state = ECS_ENABLED;
        return S_OK;
    }
    IFACEMETHODIMP Invoke(IShellItemArray* items, IBindCtx*) override {
        if (format < 0) return E_NOTIMPL;
        EXPCMDSTATE state;
        if (FAILED(GetState(items, TRUE, &state)) || state != ECS_ENABLED) return E_INVALIDARG;
        auto selected = selection->get(items);
        if (selected.empty()) return E_INVALIDARG;
        wchar_t tempFolder[MAX_PATH], request[MAX_PATH];
        if (!GetTempPathW(MAX_PATH, tempFolder) || !GetTempFileNameW(tempFolder, L"cvt", 0, request))
            return HRESULT_FROM_WIN32(GetLastError());
        HANDLE file = CreateFileW(request, GENERIC_WRITE, 0, nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
        if (file == INVALID_HANDLE_VALUE) { DeleteFileW(request); return HRESULT_FROM_WIN32(GetLastError()); }
        std::wstring data(1, 0xFEFF);
        for (auto& path : selected) data += path + L"\n";
        DWORD written = 0;
        BOOL ok = WriteFile(file, data.data(), static_cast<DWORD>(data.size() * sizeof(wchar_t)), &written, nullptr);
        CloseHandle(file);
        if (!ok || written != data.size() * sizeof(wchar_t)) { DeleteFileW(request); return E_FAIL; }
        auto executable = folder() + L"\\ConvertIt.exe";
        auto arguments = std::wstring(L"--shell --format ") + outputRules[format].id + L" --request \"" + request + L"\"";
        SHELLEXECUTEINFOW info{sizeof(info)};
        info.fMask = SEE_MASK_NOASYNC | SEE_MASK_FLAG_NO_UI;
        info.lpFile = executable.c_str();
        info.lpParameters = arguments.c_str();
        info.nShow = SW_HIDE;
        if (!ShellExecuteExW(&info)) {
            DWORD error = GetLastError(); DeleteFileW(request);
            MessageBoxW(nullptr, ukrainian() ? L"Не вдалося запустити конвертер. Перевстановіть ConvertIt." : L"Could not start the converter. Reinstall ConvertIt.", L"ConvertIt", MB_ICONERROR);
            return HRESULT_FROM_WIN32(error);
        }
        return S_OK;
    }
    IFACEMETHODIMP GetFlags(EXPCMDFLAGS* flags) override {
        if (!flags) return E_POINTER;
        *flags = format == -1 ? ECF_HASSUBCOMMANDS : ECF_DEFAULT;
        return S_OK;
    }
    IFACEMETHODIMP EnumSubCommands(IEnumExplorerCommand** out) override {
        if (!out) return E_POINTER;
        *out = nullptr;
        if (format != -1) return E_NOTIMPL;
        *out = new(std::nothrow) Enumerator(selection);
        return *out ? S_OK : E_OUTOFMEMORY;
    }
};

HRESULT Enumerator::Next(ULONG count, IExplorerCommand** commands, ULONG* fetched) {
    if (!commands || (!fetched && count != 1)) return E_POINTER;
    ULONG done = 0;
    while (done < count && position < nodes.size()) {
        commands[done] = new(std::nothrow) Command(nodes[position], selection);
        if (!commands[done]) { if (fetched) *fetched = done; return E_OUTOFMEMORY; }
        ++done; ++position;
    }
    if (fetched) *fetched = done;
    return done == count ? S_OK : S_FALSE;
}

class Factory final : public IClassFactory {
    std::atomic<ULONG> refs{1};
public:
    Factory() { ++objects; }
    ~Factory() { --objects; }
    IFACEMETHODIMP QueryInterface(REFIID iid, void** out) override {
        if (!out) return E_POINTER;
        *out = nullptr;
        if (iid == IID_IUnknown || iid == IID_IClassFactory) { *out = static_cast<IClassFactory*>(this); AddRef(); return S_OK; }
        return E_NOINTERFACE;
    }
    IFACEMETHODIMP_(ULONG) AddRef() override { return ++refs; }
    IFACEMETHODIMP_(ULONG) Release() override { ULONG n = --refs; if (!n) delete this; return n; }
    IFACEMETHODIMP CreateInstance(IUnknown* outer, REFIID iid, void** out) override {
        if (!out) return E_POINTER;
        *out = nullptr;
        if (outer) return CLASS_E_NOAGGREGATION;
        auto command = new(std::nothrow) Command();
        if (!command) return E_OUTOFMEMORY;
        HRESULT result = command->QueryInterface(iid, out); command->Release(); return result;
    }
    IFACEMETHODIMP LockServer(BOOL lock) override { if (lock) ++objects; else --objects; return S_OK; }
};
extern "C" HRESULT __stdcall DllGetClassObject(REFCLSID clsid, REFIID iid, void** out) {
    if (!out) return E_POINTER;
    *out = nullptr;
    if (clsid != CLSID_Convert) return CLASS_E_CLASSNOTAVAILABLE;
    auto factory = new(std::nothrow) Factory();
    if (!factory) return E_OUTOFMEMORY;
    HRESULT result = factory->QueryInterface(iid, out); factory->Release(); return result;
}
extern "C" HRESULT __stdcall DllCanUnloadNow() { return objects == 0 ? S_OK : S_FALSE; }
BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, void*) {
    if (reason == DLL_PROCESS_ATTACH) { moduleHandle = instance; DisableThreadLibraryCalls(instance); }
    return TRUE;
}
