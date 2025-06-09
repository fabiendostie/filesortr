import unittest
import os
import shutil
import json
import tempfile
import sys
from pathlib import Path
from typing import Dict, List, Any
import logging
from unittest.mock import patch, mock_open, MagicMock
import io

# Assuming file_sorter.py is in the same directory or accessible via PYTHONPATH
import file_sorter

class TestFileSorter(unittest.TestCase):
    """Comprehensive test suite for file_sorter module"""

    @classmethod
    def setUpClass(cls):
        """Set up class-level test configuration"""
        # Store original logging level
        cls.original_log_level = logging.getLogger().level
        # Suppress most logging during tests unless specifically needed
        logging.getLogger().setLevel(logging.CRITICAL)

    @classmethod
    def tearDownClass(cls):
        """Clean up class-level test configuration"""
        # Restore original logging level
        logging.getLogger().setLevel(cls.original_log_level)

    def setUp(self):
        """Set up test environment for each test"""
        # Create temporary directory using system temp
        self.temp_dir = Path(tempfile.mkdtemp(prefix="file_sorter_test_"))
        self.input_dir = self.temp_dir / "input"
        self.output_dir = self.temp_dir / "output"
        
        self.input_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Test configuration
        self.mock_config_data = {
            "FILE_CATEGORIES": {
                "txt": "Documents/Text",
                "jpg": "Images/Photos",
                "png": "Images/Photos",
                "py": "SourceCode/Python",
                "js": "SourceCode/JavaScript",
                "exe": "Applications/Executables",
                "zip": "Archives",
                "pdf": "Documents/PDFs",
                "mp3": "Audio/Music",
                "mp4": "Video/Common"
            },
            "DEFAULT_CATEGORY": "Miscellaneous/Other",
            "PROJECT_FILE_MARKERS": [".git", "package.json", "pom.xml", "requirements.txt"],
            "PROJECT_DIR_MARKERS": ["node_modules", ".idea", "venv", "__pycache__"],
            "APPLICATION_EXECUTABLE_EXTENSIONS": [".exe", ".msi", ".app"],
            "SPECIAL_APP_DIRS_AS_FILES": [".app"]
        }
        
        # Patch global configuration variables
        self.config_patches = [
            patch.object(file_sorter, 'FILE_CATEGORIES', self.mock_config_data['FILE_CATEGORIES']),
            patch.object(file_sorter, 'DEFAULT_CATEGORY', self.mock_config_data['DEFAULT_CATEGORY']),
            patch.object(file_sorter, 'PROJECT_FILE_MARKERS', self.mock_config_data['PROJECT_FILE_MARKERS']),
            patch.object(file_sorter, 'PROJECT_DIR_MARKERS', self.mock_config_data['PROJECT_DIR_MARKERS']),
            patch.object(file_sorter, 'APPLICATION_EXECUTABLE_EXTENSIONS', self.mock_config_data['APPLICATION_EXECUTABLE_EXTENSIONS']),
            patch.object(file_sorter, 'SPECIAL_APP_DIRS_AS_FILES', self.mock_config_data['SPECIAL_APP_DIRS_AS_FILES'])
        ]

        for patcher in self.config_patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        """Clean up test environment"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def create_file_structure(self, structure: Dict[str, Any], base_path: Path = None) -> None:
        """Create a file/directory structure from a nested dict"""
        if base_path is None:
            base_path = self.input_dir
            
        for name, content in structure.items():
            path = base_path / name
            
            if isinstance(content, dict):  # Directory
                path.mkdir(parents=True, exist_ok=True)
                self.create_file_structure(content, path)
            elif isinstance(content, str):  # File with content
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding='utf-8')
            else:  # Empty file
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()

    def capture_logs(self, level=logging.INFO) -> io.StringIO:
        """Context manager to capture log output"""
        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setLevel(level)
        
        logger = logging.getLogger()
        original_level = logger.level
        original_handlers = logger.handlers[:]
        
        logger.handlers = [handler]
        logger.setLevel(level)
        
        class LogCapture:
            def __enter__(self):
                return log_capture
            
            def __exit__(self, exc_type, exc_val, exc_tb):
                logger.handlers = original_handlers
                logger.setLevel(original_level)
        
        return LogCapture()

    # --- Configuration Tests ---
    def test_validate_config_schema_valid(self):
        """Test config schema validation with valid configuration"""
        errors = file_sorter.validate_config_schema(self.mock_config_data)
        self.assertEqual(errors, [])

    def test_validate_config_schema_missing_keys(self):
        """Test config schema validation with missing keys"""
        incomplete_config = {"FILE_CATEGORIES": {}}
        errors = file_sorter.validate_config_schema(incomplete_config)
        self.assertGreater(len(errors), 0)
        self.assertTrue(any("Missing required configuration key" in error for error in errors))

    def test_validate_config_schema_wrong_types(self):
        """Test config schema validation with wrong data types"""
        invalid_config = {
            "FILE_CATEGORIES": "not_a_dict",
            "DEFAULT_CATEGORY": 123,
            "PROJECT_FILE_MARKERS": "not_a_list",
            "PROJECT_DIR_MARKERS": [],
            "APPLICATION_EXECUTABLE_EXTENSIONS": [],
            "SPECIAL_APP_DIRS_AS_FILES": []
        }
        errors = file_sorter.validate_config_schema(invalid_config)
        self.assertGreater(len(errors), 0)

    @patch('builtins.open', new_callable=mock_open, read_data='{"FILE_CATEGORIES": {}}')
    @patch('pathlib.Path.is_file', return_value=True)
    @patch('pathlib.Path.exists', return_value=True)
    def test_load_config_invalid_json(self, mock_exists, mock_is_file, mock_file):
        """Test config loading with invalid JSON"""
        mock_file.return_value.read.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
        
        with self.capture_logs(logging.ERROR) as log_capture:
            result = file_sorter.load_config("test_config.json")
        
        self.assertFalse(result)
        self.assertIn("Invalid JSON", log_capture.getvalue())

    # --- Path Validation Tests ---
    def test_validate_input_paths_valid(self):
        """Test path validation with valid paths"""
        input_dir, output_dir = file_sorter.validate_input_paths(
            str(self.input_dir), str(self.output_dir)
        )
        self.assertEqual(input_dir, self.input_dir.resolve())
        self.assertEqual(output_dir, self.output_dir.resolve())

    def test_validate_input_paths_nonexistent_input(self):
        """Test path validation with non-existent input directory"""
        nonexistent = self.temp_dir / "nonexistent"
        with self.assertRaises(FileNotFoundError):
            file_sorter.validate_input_paths(str(nonexistent))

    def test_validate_input_paths_input_is_file(self):
        """Test path validation when input is a file not directory"""
        test_file = self.temp_dir / "test_file.txt"
        test_file.touch()
        
        with self.assertRaises(NotADirectoryError):
            file_sorter.validate_input_paths(str(test_file))

    def test_validate_input_paths_same_input_output(self):
        """Test path validation when input and output are the same"""
        with self.assertRaises(ValueError):
            file_sorter.validate_input_paths(str(self.input_dir), str(self.input_dir))

    def test_validate_input_paths_output_inside_input(self):
        """Test path validation when output is inside input"""
        nested_output = self.input_dir / "nested_output"
        with self.assertRaises(ValueError):
            file_sorter.validate_input_paths(str(self.input_dir), str(nested_output))

    def test_validate_input_paths_default_output(self):
        """Test path validation with default output directory"""
        input_dir, output_dir = file_sorter.validate_input_paths(str(self.input_dir))
        expected_output = self.input_dir.parent / f"{self.input_dir.name}_Sorted"
        self.assertEqual(output_dir, expected_output)

    # --- File Categorization Tests ---
    def test_get_category_known_extensions(self):
        """Test file categorization for known extensions"""
        test_cases = [
            ("document.txt", "Documents/Text"),
            ("photo.jpg", "Images/Photos"),
            ("script.py", "SourceCode/Python"),
            ("archive.zip", "Archives"),
            ("music.mp3", "Audio/Music"),
            ("video.mp4", "Video/Common")
        ]
        
        for filename, expected_category in test_cases:
            with self.subTest(filename=filename):
                self.assertEqual(file_sorter.get_category_for_file(filename), expected_category)

    def test_get_category_unknown_extension(self):
        """Test file categorization for unknown extensions"""
        self.assertEqual(file_sorter.get_category_for_file("unknown.xyz"), "Miscellaneous/Other")

    def test_get_category_case_insensitive(self):
        """Test file categorization is case insensitive"""
        test_cases = [
            "DOCUMENT.TXT",
            "Photo.JPG",
            "Script.PY"
        ]
        
        for filename in test_cases:
            with self.subTest(filename=filename):
                category = file_sorter.get_category_for_file(filename)
                self.assertNotEqual(category, "Miscellaneous/Other")

    def test_get_category_no_extension(self):
        """Test file categorization for files without extensions"""
        self.assertEqual(file_sorter.get_category_for_file("README"), "Miscellaneous/Other")

    def test_get_category_multiple_dots(self):
        """Test file categorization for files with multiple dots"""
        self.assertEqual(file_sorter.get_category_for_file("archive.tar.gz"), "Miscellaneous/Other")

    # --- Project Detection Tests ---
    def test_is_project_folder_git(self):
        """Test project detection for Git repositories"""
        structure = {".git": {}, "README.md": ""}
        self.create_file_structure(structure)
        
        contents = os.listdir(self.input_dir)
        self.assertTrue(file_sorter.is_project_or_app_folder(self.input_dir, contents))

    def test_is_project_folder_npm(self):
        """Test project detection for npm projects"""
        structure = {"package.json": '{"name": "test"}', "node_modules": {}}
        self.create_file_structure(structure)
        
        contents = os.listdir(self.input_dir)
        self.assertTrue(file_sorter.is_project_or_app_folder(self.input_dir, contents))

    def test_is_project_folder_python(self):
        """Test project detection for Python projects"""
        structure = {"requirements.txt": "requests==2.25.1", "venv": {}}
        self.create_file_structure(structure)
        
        contents = os.listdir(self.input_dir)
        self.assertTrue(file_sorter.is_project_or_app_folder(self.input_dir, contents))

    def test_is_app_bundle_macos(self):
        """Test detection of macOS app bundles"""
        app_dir = self.input_dir / "TestApp.app"
        app_dir.mkdir()
        
        contents = ["Contents"]
        self.assertTrue(file_sorter.is_project_or_app_folder(app_dir, contents))

    def test_is_not_project_folder(self):
        """Test that regular directories are not detected as projects"""
        structure = {"document.txt": "", "photo.jpg": "", "regular_folder": {}}
        self.create_file_structure(structure)
        
        contents = os.listdir(self.input_dir)
        self.assertFalse(file_sorter.is_project_or_app_folder(self.input_dir, contents))

    # --- File Operations Tests ---
    def test_generate_unique_filename_no_collision(self):
        """Test unique filename generation when no collision exists"""
        target = self.output_dir / "test.txt"
        result = file_sorter.generate_unique_filename(target)
        self.assertEqual(result, target)

    def test_generate_unique_filename_with_collision(self):
        """Test unique filename generation with collisions"""
        # Create existing files
        (self.output_dir / "test.txt").touch()
        (self.output_dir / "test (1).txt").touch()
        
        target = self.output_dir / "test.txt"
        result = file_sorter.generate_unique_filename(target)
        expected = self.output_dir / "test (2).txt"
        self.assertEqual(result, expected)

    def test_cache_directory_contents_success(self):
        """Test successful directory content caching"""
        structure = {"file1.txt": "", "file2.txt": "", "subdir": {}}
        self.create_file_structure(structure)
        
        contents = file_sorter.cache_directory_contents(self.input_dir)
        self.assertIsNotNone(contents)
        self.assertIn("file1.txt", contents)
        self.assertIn("file2.txt", contents)
        self.assertIn("subdir", contents)

    def test_cache_directory_contents_permission_error(self):
        """Test directory content caching with permission error"""
        with patch('os.listdir', side_effect=PermissionError("Access denied")):
            contents = file_sorter.cache_directory_contents(self.input_dir)
            self.assertIsNone(contents)

    # --- Integration Tests ---
    def test_sort_files_basic_operation(self):
        """Test basic file sorting operation"""
        structure = {
            "document.txt": "Test content",
            "photo.jpg": "",
            "unknown.xyz": "",
            "project": {
                ".git": {},
                "main.py": "print('hello')"
            },
            "regular_folder": {
                "nested.pdf": ""
            }
        }
        self.create_file_structure(structure)
        
        success = file_sorter.sort_files(str(self.input_dir), str(self.output_dir))
        self.assertTrue(success)
        
        # Check file categorization
        self.assertTrue((self.output_dir / "Documents/Text/document.txt").exists())
        self.assertTrue((self.output_dir / "Images/Photos/photo.jpg").exists())
        self.assertTrue((self.output_dir / "Miscellaneous/Other/unknown.xyz").exists())
        self.assertTrue((self.output_dir / "Documents/PDFs/nested.pdf").exists())
        
        # Check project handling
        self.assertTrue((self.output_dir / "Applications_And_Projects/project/.git").exists())
        self.assertTrue((self.output_dir / "Applications_And_Projects/project/main.py").exists())

    def test_sort_files_dry_run(self):
        """Test dry run mode doesn't actually move files"""
        structure = {
            "test.txt": "content",
            "project": {".git": {}}
        }
        self.create_file_structure(structure)
        
        with self.capture_logs(logging.INFO) as log_capture:
            success = file_sorter.sort_files(str(self.input_dir), str(self.output_dir), dry_run=True)
        
        self.assertTrue(success)
        log_output = log_capture.getvalue()
        self.assertIn("DRY RUN MODE", log_output)
        
        # Files should still exist in input
        self.assertTrue((self.input_dir / "test.txt").exists())
        self.assertTrue((self.input_dir / "project").exists())
        
        # No files should be moved
        self.assertFalse((self.output_dir / "Documents/Text/test.txt").exists())

    def test_sort_files_filename_collisions(self):
        """Test handling of filename collisions"""
        structure = {
            "file.txt": "content1",
            "folder": {
                "file.txt": "content2"
            }
        }
        self.create_file_structure(structure)
        
        success = file_sorter.sort_files(str(self.input_dir), str(self.output_dir))
        self.assertTrue(success)
        
        # Both files should exist with different names
        self.assertTrue((self.output_dir / "Documents/Text/file.txt").exists())
        self.assertTrue((self.output_dir / "Documents/Text/file (1).txt").exists())

    def test_sort_files_delete_empty_dirs(self):
        """Test deletion of empty directories"""
        structure = {
            "file.txt": "content",
            "empty_folder": {},
            "nested": {
                "deep": {
                    "file.txt": "content"
                }
            }
        }
        self.create_file_structure(structure)
        
        success = file_sorter.sort_files(
            str(self.input_dir), 
            str(self.output_dir), 
            delete_empty_dirs=True
        )
        self.assertTrue(success)
        
        # Empty directories should be removed
        self.assertFalse((self.input_dir / "empty_folder").exists())
        self.assertFalse((self.input_dir / "nested/deep").exists())
        self.assertFalse((self.input_dir / "nested").exists())
        
        # Input directory itself should remain
        self.assertTrue(self.input_dir.exists())

    def test_sort_files_with_errors(self):
        """Test sorting with simulated errors"""
        structure = {"test.txt": "content"}
        self.create_file_structure(structure)
        
        with patch('shutil.move', side_effect=PermissionError("Access denied")):
            with self.capture_logs(logging.ERROR) as log_capture:
                success = file_sorter.sort_files(str(self.input_dir), str(self.output_dir))
        
        self.assertFalse(success)  # Should return False due to errors
        log_output = log_capture.getvalue()
        self.assertIn("Failed to move file", log_output)

    # --- Edge Cases and Error Handling ---
    def test_empty_input_directory(self):
        """Test sorting an empty directory"""
        success = file_sorter.sort_files(str(self.input_dir), str(self.output_dir))
        self.assertTrue(success)

    def test_large_directory_structure(self):
        """Test sorting a large directory structure"""
        # Create a structure with many files and folders
        structure = {}
        for i in range(100):
            structure[f"file_{i}.txt"] = f"content {i}"
            structure[f"folder_{i}"] = {f"nested_{j}.py": f"code {j}" for j in range(5)}
        
        self.create_file_structure(structure)
        
        success = file_sorter.sort_files(str(self.input_dir), str(self.output_dir))
        self.assertTrue(success)

    def test_special_characters_in_filenames(self):
        """Test handling files with special characters"""
        structure = {
            "file with spaces.txt": "content",
            "file-with-dashes.txt": "content",
            "file_with_underscores.txt": "content",
            "file[with]brackets.txt": "content",
            "file(with)parentheses.txt": "content"
        }
        self.create_file_structure(structure)
        
        success = file_sorter.sort_files(str(self.input_dir), str(self.output_dir))
        self.assertTrue(success)
        
        # All files should be moved successfully
        for filename in structure.keys():
            expected_path = self.output_dir / "Documents/Text" / filename
            self.assertTrue(expected_path.exists(), f"File {filename} was not moved correctly")

    def test_nested_project_structures(self):
        """Test handling of nested project structures"""
        structure = {
            "outer_project": {
                ".git": {},
                "src": {
                    "inner_project": {
                        "package.json": '{"name": "inner"}',
                        "index.js": "console.log('hello');"
                    }
                }
            }
        }
        self.create_file_structure(structure)
        
        success = file_sorter.sort_files(str(self.input_dir), str(self.output_dir))
        self.assertTrue(success)
        
        # The outer project should be moved as a whole
        self.assertTrue((self.output_dir / "Applications_And_Projects/outer_project/.git").exists())
        self.assertTrue((self.output_dir / "Applications_And_Projects/outer_project/src/inner_project/package.json").exists())

    @patch('os.walk')
    def test_oswalk_permission_error(self, mock_walk):
        """Test handling of permission errors during directory traversal"""
        mock_walk.side_effect = PermissionError("Permission denied")
        
        with self.capture_logs(logging.ERROR) as log_capture:
            success = file_sorter.sort_files(str(self.input_dir), str(self.output_dir))
        
        # Should handle the error gracefully
        self.assertFalse(success)

    def test_symlink_handling(self):
        """Test handling of symbolic links (if supported by OS)"""
        if os.name == 'nt':  # Skip on Windows where symlinks need special permissions
            self.skipTest("Symlink test skipped on Windows")
        
        structure = {"target.txt": "content"}
        self.create_file_structure(structure)
        
        # Create a symlink
        link_path = self.input_dir / "link.txt"
        target_path = self.input_dir / "target.txt"
        
        try:
            os.symlink(target_path, link_path)
        except OSError:
            self.skipTest("Symlinks not supported on this system")
        
        success = file_sorter.sort_files(str(self.input_dir), str(self.output_dir))
        self.assertTrue(success)
        
        # Both target and link should be processed
        self.assertTrue((self.output_dir / "Documents/Text/target.txt").exists())
        self.assertTrue((self.output_dir / "Documents/Text/link.txt").exists())

    # --- Progress Reporting Tests ---
    def test_progress_reporting(self):
        """Test progress reporting functionality"""
        structure = {f"file_{i}.txt": "content" for i in range(10)}
        self.create_file_structure(structure)
        
        with self.capture_logs(logging.INFO) as log_capture:
            success = file_sorter.sort_files(str(self.input_dir), str(self.output_dir))
        
        self.assertTrue(success)
        log_output = log_capture.getvalue()
        self.assertIn("items", log_output)  # Should mention processing items
        self.assertIn("completed", log_output)  # Should report completion

if __name__ == '__main__':
    # Configure test runner
    unittest.main(verbosity=2, buffer=True)
