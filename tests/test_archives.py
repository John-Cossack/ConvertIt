from pathlib import Path
import io
import os
import stat
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from archive_convert import binary, inventory, planned_outputs, unpack
from capabilities import available, input_extension, selection_groups
from converter import convert, shell_convert
from external_tools import run_tool


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent.parent/'test-results', prefix='archive-test-')
        self.root = Path(self.temp.name)
        self.source = self.root/'Архів & тест.zip'
        with zipfile.ZipFile(self.source, 'w') as archive:
            archive.writestr('Папка/Український текст.txt', 'Ї є ґ\n'.encode('utf-8'))
            archive.writestr('binary.bin', bytes(range(256))*50)
            archive.writestr('empty/', b'')
            archive.writestr('zero.txt', b'')
        self.original = self.source.read_bytes()
        self.expected = inventory(unpack(self.source, self.root/'reference'))

    def tearDown(self):
        self.assertEqual(self.source.read_bytes(), self.original)
        self.temp.cleanup()

    def test_every_output_and_every_output_as_input(self):
        for row in available('ARCHIVE', 'archive'):
            target = row['id']
            with self.subTest(target=target):
                source = self.source
                if target == 'zip':
                    source = self.root/'Zip source.7z'
                    if not source.exists():
                        convert(self.source, '7z').rename(source)
                result = convert(source, target)
                self.assertTrue(result.is_file())
                self.assertEqual(inventory(unpack(result, self.root/('check-'+target), target.startswith('tar.'))), self.expected)
                # Different basename allows an independent roundtrip to ZIP.
                renamed = self.root/('roundtrip-'+target+'.'+target)
                result.rename(renamed)
                back = convert(renamed, 'zip' if target != 'zip' else '7z')
                self.assertEqual(inventory(unpack(back, self.root/('back-'+target))), self.expected)

    def test_compound_name_and_collision(self):
        archive = convert(self.source, 'tar.gz')
        self.assertEqual(archive.name, 'Архів & тест.tar.gz')
        self.assertEqual(input_extension(archive), 'tar.gz')
        self.assertEqual(planned_outputs(archive, '7z')[0].name, 'Архів & тест.7z')
        with self.assertRaises(ValueError):
            convert(archive, 'tar.gz')
        destination = self.source.with_suffix('.7z')
        destination.write_bytes(b'KEEP')
        with self.assertRaises(FileExistsError):
            convert(self.source, '7z')
        self.assertEqual(destination.read_bytes(), b'KEEP')
        convert(self.source, '7z', overwrite=True)
        self.assertNotEqual(destination.read_bytes(), b'KEEP')

    def test_unsafe_zip_names_and_case_collisions(self):
        for index, names in enumerate([['../outside.txt'], ['/absolute.txt'], ['C:/outside.txt'], ['folder/a:stream'],
                                       ['NUL.txt'], ['name.'], ['foo.txt', 'FOO.txt'], ['line\nbreak']]):
            with self.subTest(names=names):
                source = self.root/f'bad-{index}.zip'
                with zipfile.ZipFile(source, 'w') as archive:
                    for name in names:
                        archive.writestr(name, b'data')
                with self.assertRaises(ValueError):
                    convert(source, '7z')
                self.assertFalse(source.with_suffix('.7z').exists())
        self.assertFalse((self.root.parent/'outside.txt').exists())
        self.assertFalse(list(self.root.glob('.convert-archive-*')))

    def test_links_and_special_files_rejected(self):
        for kind in [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE]:
            source = self.root/('link-'+str(kind[0])+'.tar')
            with tarfile.open(source, 'w') as archive:
                entry = tarfile.TarInfo('link')
                entry.type = kind
                entry.linkname = '../outside.txt'
                archive.addfile(entry)
            with self.assertRaises(ValueError):
                convert(source, 'zip')
        source = self.root/'symlink.zip'
        with zipfile.ZipFile(source, 'w') as archive:
            info = zipfile.ZipInfo('link')
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, '../outside.txt')
        with self.assertRaises(ValueError):
            convert(source, '7z')

    def test_encrypted_and_corrupt_archives_fail_without_output(self):
        payload = self.root/'secret.txt'
        payload.write_bytes(b'secret')
        source = self.root/'protected.7z'
        run_tool([binary(), 'a', '-t7z', '-psecret', '-mhe=on', source, payload], self.root/'encrypt')
        with self.assertRaises(ValueError):
            convert(source, 'zip')
        self.assertFalse(source.with_suffix('.zip').exists())
        source = self.root/'broken.zip'
        source.write_bytes(b'PK broken contents')
        with self.assertRaises(ValueError):
            convert(source, '7z')
        self.assertFalse(source.with_suffix('.7z').exists())

    def test_empty_archive(self):
        source = self.root/'empty.zip'
        with zipfile.ZipFile(source, 'w'):
            pass
        for target in ['7z', 'tar.gz', 'cpio']:
            with self.subTest(target=target):
                result = convert(source, target)
                self.assertEqual(inventory(unpack(result, self.root/('empty-'+target))), {})

    def test_native_worker_is_silent_and_uses_compound_basename(self):
        source = convert(self.source, 'tar.gz')
        with patch('converter.ctypes.windll.user32.MessageBoxW') as dialog:
            self.assertEqual(shell_convert([source], '7z'), 0)
            dialog.assert_not_called()
        self.assertTrue(self.source.with_suffix('.7z').exists())
        self.assertFalse(source.with_suffix('.7z').exists())

    def test_routes_are_archive_only(self):
        self.assertEqual(len(available('ARCHIVE', 'archive')), 30)
        self.assertEqual(selection_groups([self.source, self.root/'image.jpg']), [])
        with self.assertRaises(ValueError):
            planned_outputs(self.source, 'png')

    def test_failed_verification_preserves_existing_output(self):
        target = self.source.with_suffix('.tar')
        target.write_bytes(b'KEEP')
        from archive_convert import inventory as real_inventory
        def altered(path):
            values = real_inventory(path)
            if 'verify' in Path(path).parts:
                values['fake.txt'] = (1, 'incorrect')
            return values
        with patch('archive_convert.inventory', side_effect=altered):
            with self.assertRaises(ValueError):
                convert(self.source, 'tar', overwrite=True)
        self.assertEqual(target.read_bytes(), b'KEEP')
        self.assertFalse(list(self.root.glob('.convert-archive-*')))
