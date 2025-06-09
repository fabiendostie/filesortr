import os
import shutil
import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple, Any
import logging
from dataclasses import dataclass
import time

# --- Configuration Schema and Validation ---
CONFIG_SCHEMA = {
    "FILE_CATEGORIES": dict,
    "DEFAULT_CATEGORY": str,
    "PROJECT_FILE_MARKERS": list,
    "PROJECT_DIR_MARKERS": list,
    "APPLICATION_EXECUTABLE_EXTENSIONS": list,
    "SPECIAL_APP_DIRS_AS_FILES": list
}

@dataclass
class SortingProgress:
    """Track progress of file sorting operation"""
    total_items: int = 0
    processed_items: int = 0
    projects_moved: int = 0
    files_moved: int = 0
    errors: int = 0
    start_time: float = 0.0

    def report_progress(self) -> None:
        """Log current progress"""
        if self.total_items > 0:
            percentage = (self.processed_items / self.total_items) * 100
            elapsed = time.time() - self.start_time
            logging.info(f"Progress: {self.processed_items}/{self.total_items} ({percentage:.1f}%) "
                        f"- Projects: {self.projects_moved}, Files: {self.files_moved}, "
                        f"Errors: {self.errors}, Elapsed: {elapsed:.1f}s")

# --- Configuration Loading with Validation ---
# Fallback defaults
DEFAULT_FILE_CATEGORIES = {"txt": "Documents/Text"}
DEFAULT_PROJECT_FILE_MARKERS = [".git"]
DEFAULT_PROJECT_DIR_MARKERS = ["node_modules"]
DEFAULT_APPLICATION_EXECUTABLE_EXTENSIONS = [".exe"]
DEFAULT_SPECIAL_APP_DIRS_AS_FILES = [".app"]
DEFAULT_DEFAULT_CATEGORY = "Miscellaneous/Other"

# Global configuration variables
FILE_CATEGORIES: Dict[str, str] = {}
DEFAULT_CATEGORY: str = ""
PROJECT_FILE_MARKERS: List[str] = []
PROJECT_DIR_MARKERS: List[str] = []
APPLICATION_EXECUTABLE_EXTENSIONS: List[str] = []
SPECIAL_APP_DIRS_AS_FILES: List[str] = []

def validate_config_schema(config_data: Dict[str, Any]) -> List[str]:
    """Validate configuration against expected schema"""
    errors = []
    
    for key, expected_type in CONFIG_SCHEMA.items():
        if key not in config_data:
            errors.append(f"Missing required configuration key: {key}")
        elif not isinstance(config_data[key], expected_type):
            errors.append(f"Configuration key '{key}' must be of type {expected_type.__name__}")
    
    # Additional validation
    if "FILE_CATEGORIES" in config_data:
        file_cats = config_data["FILE_CATEGORIES"]
        if not all(isinstance(k, str) and isinstance(v, str) for k, v in file_cats.items()):
            errors.append("FILE_CATEGORIES must contain only string key-value pairs")
    
    return errors

def load_config(config_path_str: Optional[str] = None) -> bool:
    """Load configuration with validation and better error handling"""
    global FILE_CATEGORIES, DEFAULT_CATEGORY, PROJECT_FILE_MARKERS, PROJECT_DIR_MARKERS
    global APPLICATION_EXECUTABLE_EXTENSIONS, SPECIAL_APP_DIRS_AS_FILES

    # Initialize with hardcoded fallbacks
    FILE_CATEGORIES = DEFAULT_FILE_CATEGORIES.copy()
    DEFAULT_CATEGORY = DEFAULT_DEFAULT_CATEGORY
    PROJECT_FILE_MARKERS = DEFAULT_PROJECT_FILE_MARKERS.copy()
    PROJECT_DIR_MARKERS = DEFAULT_PROJECT_DIR_MARKERS.copy()
    APPLICATION_EXECUTABLE_EXTENSIONS = DEFAULT_APPLICATION_EXECUTABLE_EXTENSIONS.copy()
    SPECIAL_APP_DIRS_AS_FILES = DEFAULT_SPECIAL_APP_DIRS_AS_FILES.copy()

    config_paths_to_try = []
    if config_path_str:
        config_paths_to_try.append(Path(config_path_str))
    
    # Try to find default_config.json in standard locations
    config_paths_to_try.extend([
        Path.cwd() / "default_config.json",
        Path(__file__).parent.resolve() / "default_config.json" if '__file__' in globals() else None
    ])
    
    # Filter out None values
    config_paths_to_try = [p for p in config_paths_to_try if p is not None]

    loaded_config_path = None
    for config_path in config_paths_to_try:
        try:
            if config_path.is_file() and config_path.exists():
                loaded_config_path = config_path
                break
        except (OSError, PermissionError) as e:
            logging.debug(f"Could not access config path {config_path}: {e}")
            continue
            
    if not loaded_config_path:
        logging.warning("No configuration file found. Using hardcoded defaults.")
        return False

    try:
        logging.info(f"Loading configuration from: {loaded_config_path}")
        with open(loaded_config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        
        # Validate configuration schema
        validation_errors = validate_config_schema(config_data)
        if validation_errors:
            logging.error(f"Configuration validation failed: {'; '.join(validation_errors)}")
            logging.warning("Using fallback defaults due to invalid configuration.")
            return False
        
        # Load validated configuration
        FILE_CATEGORIES = config_data.get("FILE_CATEGORIES", DEFAULT_FILE_CATEGORIES).copy()
        DEFAULT_CATEGORY = config_data.get("DEFAULT_CATEGORY", DEFAULT_DEFAULT_CATEGORY)
        PROJECT_FILE_MARKERS = config_data.get("PROJECT_FILE_MARKERS", DEFAULT_PROJECT_FILE_MARKERS).copy()
        PROJECT_DIR_MARKERS = config_data.get("PROJECT_DIR_MARKERS", DEFAULT_PROJECT_DIR_MARKERS).copy()
        APPLICATION_EXECUTABLE_EXTENSIONS = config_data.get("APPLICATION_EXECUTABLE_EXTENSIONS", DEFAULT_APPLICATION_EXECUTABLE_EXTENSIONS).copy()
        SPECIAL_APP_DIRS_AS_FILES = config_data.get("SPECIAL_APP_DIRS_AS_FILES", DEFAULT_SPECIAL_APP_DIRS_AS_FILES).copy()
        
        logging.info("Configuration loaded and validated successfully.")
        return True

    except (FileNotFoundError, PermissionError) as e:
        logging.error(f"Cannot access configuration file '{loaded_config_path}': {e}")
    except json.JSONDecodeError as e:
        logging.error(f"Invalid JSON in configuration file '{loaded_config_path}': {e}")
    except Exception as e:
        logging.error(f"Unexpected error loading configuration from '{loaded_config_path}': {e}")
    
    logging.warning("Using fallback defaults due to configuration loading failure.")
    return False

# --- Core Functions ---
def validate_input_paths(input_dir_str: str, output_dir_str: Optional[str] = None) -> Tuple[Path, Path]:
    """Validate and resolve input/output paths"""
    input_dir = Path(input_dir_str).resolve()
    
    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory '{input_dir}' does not exist")
    
    if not input_dir.is_dir():
        raise NotADirectoryError(f"Input path '{input_dir}' is not a directory")
    
    # Check read permissions
    try:
        os.listdir(input_dir)
    except PermissionError:
        raise PermissionError(f"No read permission for input directory '{input_dir}'")
    
    if output_dir_str:
        output_dir = Path(output_dir_str).resolve()
    else:
        output_dir = input_dir.parent / f"{input_dir.name}_Sorted"
    
    # Ensure input and output are not the same
    if input_dir == output_dir:
        raise ValueError("Input and output directories cannot be the same")
    
    # Check if output is inside input (would cause infinite recursion)
    try:
        output_dir.relative_to(input_dir)
        raise ValueError("Output directory cannot be inside input directory")
    except ValueError:
        pass  # This is expected - output is not inside input
    
    return input_dir, output_dir

def get_category_for_file(filename: str) -> str:
    """Get category path for a file based on its extension"""
    extension = Path(filename).suffix.lower().lstrip('.')
    return FILE_CATEGORIES.get(extension, DEFAULT_CATEGORY)

def cache_directory_contents(directory: Path) -> Optional[List[str]]:
    """Safely cache directory contents with error handling"""
    try:
        return os.listdir(directory)
    except (OSError, PermissionError) as e:
        logging.warning(f"Cannot read directory '{directory}': {e}")
        return None

def is_project_or_app_folder(dir_path: Path, dir_contents: List[str]) -> bool:
    """Determine if a directory is a project or app folder"""
    dir_name = dir_path.name
    
    # Check for special app directories (e.g., .app bundles)
    if any(dir_name.endswith(suffix) for suffix in SPECIAL_APP_DIRS_AS_FILES):
        return True
    
    # Check for project markers in directory contents
    for item_name in dir_contents:
        if item_name in PROJECT_FILE_MARKERS or item_name in PROJECT_DIR_MARKERS:
            return True
    
    return False

def count_items_to_process(input_dir: Path) -> int:
    """Count total items to process for progress reporting"""
    total = 0
    try:
        for root, dirs, files in os.walk(input_dir):
            total += len(files) + len(dirs)
    except (OSError, PermissionError):
        # If we can't count, return 0 to disable progress reporting
        return 0
    return total

def identify_projects(input_dir: Path, processed_projects: Set[Path]) -> List[Tuple[Path, Path]]:
    """Identify project directories that need to be moved"""
    projects_to_move = []
    
    try:
        for root, dirs, _ in os.walk(input_dir, topdown=True):
            current_root_path = Path(root)
            
            # Skip if already processed
            if any(processed == current_root_path or processed in current_root_path.parents 
                   for processed in processed_projects):
                dirs[:] = []  # Don't descend further
                continue
            
            # Check current directory
            dir_contents = cache_directory_contents(current_root_path)
            if dir_contents and is_project_or_app_folder(current_root_path, dir_contents):
                target_path = current_root_path.parent / "Applications_And_Projects" / current_root_path.name
                projects_to_move.append((current_root_path, target_path))
                dirs[:] = []  # Don't descend into project
                continue
            
            # Check subdirectories
            dirs_to_remove = []
            for dir_name in dirs:
                sub_dir_path = current_root_path / dir_name
                
                # Skip if already processed
                if any(processed == sub_dir_path or processed in sub_dir_path.parents 
                       for processed in processed_projects):
                    dirs_to_remove.append(dir_name)
                    continue
                
                sub_dir_contents = cache_directory_contents(sub_dir_path)
                if sub_dir_contents and is_project_or_app_folder(sub_dir_path, sub_dir_contents):
                    target_path = current_root_path / "Applications_And_Projects" / dir_name
                    projects_to_move.append((sub_dir_path, target_path))
                    dirs_to_remove.append(dir_name)  # Don't descend into project
            
            # Remove processed directories from traversal
            for dir_name in dirs_to_remove:
                if dir_name in dirs:
                    dirs.remove(dir_name)
                    
    except (OSError, PermissionError) as e:
        logging.error(f"Error during project identification: {e}")
    
    return projects_to_move

def move_project(source: Path, destination: Path, output_dir: Path, dry_run: bool = False) -> bool:
    """Move a project directory to the output location"""
    target_project_dir = output_dir / destination.relative_to(source.parent)
    
    logging.info(f"[Project] Moving '{source}' -> '{target_project_dir}'")
    
    if dry_run:
        return True
    
    try:
        target_project_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target_project_dir))
        return True
    except (OSError, PermissionError, shutil.Error) as e:
        logging.error(f"Failed to move project '{source}': {e}")
        return False

def generate_unique_filename(target_file_path: Path) -> Path:
    """Generate a unique filename to avoid collisions"""
    if not target_file_path.exists():
        return target_file_path
    
    stem = target_file_path.stem
    suffix = target_file_path.suffix
    parent = target_file_path.parent
    counter = 1
    
    while True:
        new_path = parent / f"{stem} ({counter}){suffix}"
        if not new_path.exists():
            return new_path
        counter += 1
        
        # Prevent infinite loops
        if counter > 10000:
            logging.error(f"Too many filename collisions for '{target_file_path}'")
            return target_file_path

def categorize_and_move_file(file_path: Path, output_dir: Path, dry_run: bool = False) -> bool:
    """Categorize and move a single file"""
    category_path_str = get_category_for_file(file_path.name)
    target_file_dir = output_dir / category_path_str
    target_file_path = generate_unique_filename(target_file_dir / file_path.name)
    
    logging.debug(f"'{file_path}' -> '{target_file_path}'")
    
    if dry_run:
        return True
    
    try:
        target_file_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(file_path), str(target_file_path))
        return True
    except (OSError, PermissionError, shutil.Error) as e:
        logging.error(f"Failed to move file '{file_path}': {e}")
        return False

def cleanup_empty_directories(input_dir: Path, directories_to_check: Set[Path], dry_run: bool = False) -> int:
    """Clean up empty directories after file operations"""
    if dry_run:
        return 0
    
    logging.info("Cleaning up empty directories...")
    deleted_count = 0
    
    # Sort by depth (deepest first) to handle nested empty directories
    sorted_dirs = sorted(directories_to_check, key=lambda p: len(p.parts), reverse=True)
    
    for dir_path in sorted_dirs:
        # Don't delete the input directory itself
        if dir_path == input_dir:
            continue
            
        try:
            if dir_path.exists() and dir_path.is_dir():
                # Check if directory is empty
                if not any(dir_path.iterdir()):
                    logging.debug(f"Deleting empty directory: '{dir_path}'")
                    dir_path.rmdir()
                    deleted_count += 1
        except (OSError, PermissionError) as e:
            logging.debug(f"Could not delete directory '{dir_path}': {e}")
    
    if deleted_count > 0:
        logging.info(f"Deleted {deleted_count} empty directories")
    
    return deleted_count

def sort_files(input_dir_str: str, output_dir_str: Optional[str] = None, 
               dry_run: bool = False, delete_empty_dirs: bool = False) -> bool:
    """Main function to sort files with improved error handling and progress reporting"""
    
    try:
        # Validate input paths
        input_dir, output_dir = validate_input_paths(input_dir_str, output_dir_str)
    except (FileNotFoundError, NotADirectoryError, PermissionError, ValueError) as e:
        logging.error(f"Path validation failed: {e}")
        return False
    
    logging.info(f"Starting file sort from '{input_dir}' to '{output_dir}'")
    if dry_run:
        logging.info("DRY RUN MODE: No files will actually be moved")
    if delete_empty_dirs:
        logging.info("Empty source directories will be removed after sorting")
    
    # Initialize progress tracking
    progress = SortingProgress()
    progress.total_items = count_items_to_process(input_dir)
    progress.start_time = time.time()
    
    if progress.total_items > 0:
        logging.info(f"Processing {progress.total_items} items")
    
    processed_projects: Set[Path] = set()
    directories_to_check: Set[Path] = set()
    
    try:
        # Phase 1: Identify and move projects
        logging.info("Phase 1: Identifying project directories...")
        projects_to_move = identify_projects(input_dir, processed_projects)
        
        for source_path, _ in projects_to_move:
            if move_project(source_path, _, output_dir, dry_run):
                processed_projects.add(source_path)
                progress.projects_moved += 1
            else:
                progress.errors += 1
            
            progress.processed_items += 1
            if progress.total_items > 100 and progress.processed_items % 10 == 0:
                progress.report_progress()
        
        # Phase 2: Process remaining files
        logging.info("Phase 2: Processing individual files...")
        for root, dirs, files in os.walk(input_dir, topdown=True):
            current_root_path = Path(root)
            
            # Skip processed project directories
            if any(processed in current_root_path.parents or processed == current_root_path 
                   for processed in processed_projects):
                dirs[:] = []
                continue
            
            # Track directories for cleanup
            if delete_empty_dirs:
                directories_to_check.add(current_root_path)
            
            # Process files
            for filename in files:
                file_path = current_root_path / filename
                
                # Skip if part of processed project
                if any(processed in file_path.parents for processed in processed_projects):
                    continue
                
                if categorize_and_move_file(file_path, output_dir, dry_run):
                    progress.files_moved += 1
                else:
                    progress.errors += 1
                
                progress.processed_items += 1
                if progress.total_items > 100 and progress.processed_items % 50 == 0:
                    progress.report_progress()
        
        # Phase 3: Cleanup empty directories
        if delete_empty_dirs:
            logging.info("Phase 3: Cleaning up empty directories...")
            deleted_dirs = cleanup_empty_directories(input_dir, directories_to_check, dry_run)
            if deleted_dirs > 0:
                logging.info(f"Cleaned up {deleted_dirs} empty directories")
        
        # Final progress report
        elapsed_time = time.time() - progress.start_time
        logging.info(f"File sorting completed in {elapsed_time:.1f}s. "
                    f"Projects moved: {progress.projects_moved}, "
                    f"Files moved: {progress.files_moved}, "
                    f"Errors: {progress.errors}")
        
        return progress.errors == 0
        
    except Exception as e:
        logging.error(f"Unexpected error during file sorting: {e}")
        return False

def main():
    """Main entry point with improved argument parsing and logging setup"""
    
    # Setup argument parser
    parser = argparse.ArgumentParser(
        description="Sort files by type and handle project folders intelligently.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s /path/to/messy/folder
  %(prog)s /path/to/source -o /path/to/destination --dry-run
  %(prog)s /path/to/source --delete-empty-dirs --verbose
        """
    )
    
    parser.add_argument("input_dir", 
                       help="Directory containing files to be sorted")
    parser.add_argument("-o", "--output-dir", 
                       help="Output directory for sorted files (default: input_dir_Sorted)")
    parser.add_argument("--dry-run", action="store_true",
                       help="Show what would be done without making changes")
    parser.add_argument("--delete-empty-dirs", action="store_true",
                       help="Remove empty directories after sorting")
    parser.add_argument("--config", 
                       help="Path to custom JSON configuration file")
    parser.add_argument("-v", "--verbose", action="store_true",
                       help="Enable verbose logging")
    parser.add_argument("--log-file", 
                       help="Write logs to specified file")
    parser.add_argument("--progress", action="store_true",
                       help="Show progress during processing")

    args = parser.parse_args()

    # Setup logging
    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    log_level = logging.DEBUG if args.verbose else logging.INFO
    
    # Configure root logger
    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[]
    )
    
    logger = logging.getLogger()
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter(log_format))
    logger.addHandler(console_handler)
    
    # File handler if specified
    if args.log_file:
        try:
            file_handler = logging.FileHandler(args.log_file, mode='w', encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(logging.Formatter(log_format))
            logger.addHandler(file_handler)
            logging.info(f"Logging to file: {args.log_file}")
        except (OSError, PermissionError) as e:
            logging.error(f"Cannot create log file '{args.log_file}': {e}")
            return 1

    # Load configuration
    if not load_config(args.config):
        logging.warning("Configuration loading failed, but continuing with defaults")

    # Perform file sorting
    try:
        success = sort_files(
            args.input_dir, 
            args.output_dir, 
            args.dry_run, 
            args.delete_empty_dirs
        )
        return 0 if success else 1
        
    except KeyboardInterrupt:
        logging.info("Operation cancelled by user")
        return 130
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
