#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shobjidl.h>
#include <shlobj.h>
#include <cstdio>
#include <string>
#include <vector>
#include <set>
#include <cwctype>
#include "Routes.generated.h"

const CLSID CLSID_Convert = {0x5e925d56,0x17c4,0x4cb1,{0x9c,0x91,0x70,0xb5,0xc5,0xb5,0x5e,0x62}};
void check(HRESULT result, const char* step) {
    if (FAILED(result)) { printf("FAIL %s: 0x%08lX\n", step, result); fflush(stdout); ExitProcess(1); }
}
IShellItemArray* selection(const wchar_t* path) {
    IShellItem* item = nullptr;
    check(SHCreateItemFromParsingName(path, nullptr, IID_PPV_ARGS(&item)), "shell item");
    IShellItemArray* array = nullptr;
    check(SHCreateShellItemArrayFromShellItem(item, IID_PPV_ARGS(&array)), "shell array");
    item->Release(); return array;
}
int inspect(IExplorerCommand* parent, IShellItemArray* items, const wchar_t* invoke, int depth = 0) {
    IEnumExplorerCommand* enumerator = nullptr;
    check(parent->EnumSubCommands(&enumerator), "enumeration");
    int leaves = 0;
    std::set<std::wstring> inputFormats;
    DWORD count = 0;
    if (items && SUCCEEDED(items->GetCount(&count))) for (DWORD index = 0; index < count; ++index) {
        IShellItem* source = nullptr;
        check(items->GetItemAt(index, &source), "source item");
        PWSTR path = nullptr;
        check(source->GetDisplayName(SIGDN_FILESYSPATH, &path), "source path");
        std::wstring filename(path);
        CoTaskMemFree(path); source->Release();
        auto dot = filename.find_last_of(L'.');
        auto suffix = dot == std::wstring::npos ? L"" : filename.substr(dot);
        for (auto& c : suffix) c = towlower(c);
        for (auto& c : filename) c = towlower(c);
        for (auto& rule : inputRules) {
            std::wstring candidate(rule.extension);
            if (candidate.size() > suffix.size() && filename.size() >= candidate.size()
                && filename.compare(filename.size()-candidate.size(), candidate.size(), candidate) == 0)
                suffix = candidate;
        }
        auto inputFormat = suffix.size() ? suffix.substr(1) : L"";
        if (inputFormat == L"jpeg" || inputFormat == L"jpe" || inputFormat == L"jfif") inputFormat = L"jpg";
        if (inputFormat == L"tif") inputFormat = L"tiff";
        if (inputFormat == L"apng") inputFormat = L"png";
        if (inputFormat == L"dib") inputFormat = L"bmp";
        if (inputFormat == L"htm") inputFormat = L"html";
        if (inputFormat == L"markdown") inputFormat = L"md";
        for (auto& c : inputFormat) c = towupper(c);
        inputFormats.insert(inputFormat);
    }
    std::set<std::wstring> captions;
    IExplorerCommand* child = nullptr;
    while (enumerator->Next(1, &child, nullptr) == S_OK) {
        PWSTR name = nullptr;
        check(child->GetTitle(nullptr, &name), "child title with inherited selection");
        EXPCMDSTATE state;
        check(child->GetState(nullptr, TRUE, &state), "child state with inherited selection");
        if (state != ECS_HIDDEN) {
            wprintf(L"%*s%s: %u\n", depth * 2, L"", name, state);
            EXPCMDFLAGS flags;
            check(child->GetFlags(&flags), "child flags");
            if (flags & ECF_HASSUBCOMMANDS) {
                check(E_FAIL, "Explorer does not support nested subcommands");
            } else {
                ++leaves;
                if (!captions.insert(name).second) check(E_FAIL, "duplicate format title");
                for (auto c : std::wstring(name))
                    if (!((c >= L'A' && c <= L'Z') || (c >= L'0' && c <= L'9') || c == L'.'))
                        check(E_FAIL, "format titles must contain only the format name");
                PWSTR tip = nullptr;
                check(child->GetToolTip(nullptr, &tip), "format tooltip");
                if (std::wstring(tip) != name) check(E_FAIL, "unexpected format explanation");
                CoTaskMemFree(tip);
                if (state != ECS_ENABLED) check(E_FAIL, "menu must contain only active conversions");
                if (inputFormats.count(name) != 0) check(E_FAIL, "input format must be hidden");
                if (std::wstring(name) == L"HEIC" || std::wstring(name) == L"HEIF") check(E_FAIL, "HEIC output must stay absent");
                if (invoke && (std::wstring(name) == invoke || std::wstring(name).rfind(std::wstring(invoke)+L" — ", 0) == 0)) {
                    check(child->Invoke(nullptr, nullptr), "invoke with inherited selection");
                    printf("Invoked converter\n");
                }
            }
        }
        CoTaskMemFree(name);
        child->Release();
    }
    enumerator->Reset();
    IEnumExplorerCommand* clone = nullptr;
    check(enumerator->Clone(&clone), "clone");
    clone->Release();
    enumerator->Release();
    return leaves;
}
int wmain(int argc, wchar_t** argv) {
    if (argc < 3) return 2;
    if (std::wstring(argv[argc-1]) == L"--without-winrar") {
        SetEnvironmentVariableW(L"ProgramFiles", L"D:\\PROJECTS\\convert-app\\test-results\\no-winrar");
        SetEnvironmentVariableW(L"ProgramFiles(x86)", L"D:\\PROJECTS\\convert-app\\test-results\\no-winrar");
    }
    check(CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED), "COM init");
    IExplorerCommand* root = nullptr;
    HMODULE module = nullptr;
    if (std::wstring(argv[1]) == L"--registered") {
        check(CoCreateInstance(CLSID_Convert, nullptr, CLSCTX_LOCAL_SERVER, IID_PPV_ARGS(&root)), "registered activation");
    } else {
        module = LoadLibraryW(argv[1]);
        if (!module) { printf("LoadLibrary: %lu\n", GetLastError()); return 1; }
        auto entry = reinterpret_cast<HRESULT(WINAPI*)(REFCLSID, REFIID, void**)>(GetProcAddress(module, "DllGetClassObject"));
        IClassFactory* factory = nullptr;
        check(entry(CLSID_Convert, IID_PPV_ARGS(&factory)), "class factory");
        check(factory->CreateInstance(nullptr, IID_PPV_ARGS(&root)), "command creation");
        factory->Release();
    }
    auto items = selection(argv[2]);
    if (argc >= 5 && std::wstring(argv[3]) == L"--with") {
        PIDLIST_ABSOLUTE ids[2]{};
        check(SHParseDisplayName(argv[2], nullptr, &ids[0], 0, nullptr), "first mixed path");
        check(SHParseDisplayName(argv[4], nullptr, &ids[1], 0, nullptr), "second mixed path");
        PCIDLIST_ABSOLUTE immutable[2] = {ids[0], ids[1]};
        IShellItemArray* mixed = nullptr;
        check(SHCreateShellItemArrayFromIDLists(2, immutable, &mixed), "mixed selection");
        CoTaskMemFree(ids[0]); CoTaskMemFree(ids[1]);
        items->Release(); items = mixed;
    }
    EXPCMDSTATE state;
    check(root->GetState(items, TRUE, &state), "image state");
    printf("Root state: %u\n", state);
    if (state != ECS_ENABLED) return 1;
    EXPCMDFLAGS flags;
    check(root->GetFlags(&flags), "root flags");
    if (!(flags & ECF_HASSUBCOMMANDS)) return 1;
    PWSTR title = nullptr;
    check(root->GetTitle(items, &title), "root title");
    const wchar_t* expectedTitle = PRIMARYLANGID(GetUserDefaultUILanguage()) == LANG_UKRAINIAN ? L"Конвертувати" : L"Convert";
    if (std::wstring(title) != expectedTitle) return 1;
    CoTaskMemFree(title);
    int visible = inspect(root, items, argc >= 5 && std::wstring(argv[3]) == L"--invoke" ? argv[4] : nullptr);
    if (visible < 1 || visible > 256) return 1;
    if (argc >= 4 && std::wstring(argv[argc-1]) == L"--wait") {
        printf("Waiting for UI verification; press Enter to finish\n");
        fflush(stdout);
        getchar();
    }
    auto unsupported = selection(L"D:\\PROJECTS\\convert-app\\package\\AppxManifest.xml");
    check(root->GetState(unsupported, TRUE, &state), "unsupported state");
    if (state != ECS_HIDDEN) return 1;
    unsupported->Release(); items->Release(); root->Release();
    if (module) {
        auto unload = reinterpret_cast<HRESULT(WINAPI*)()>(GetProcAddress(module, "DllCanUnloadNow"));
        if (unload() != S_OK) return 1;
        FreeLibrary(module);
    }
    CoUninitialize();
    printf("PASS: flat Explorer submenu, %d entries, input formats hidden, no disabled entries, no HEIC encoding, states, COM lifetime\n", visible);
    return 0;
}
