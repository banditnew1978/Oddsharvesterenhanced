import csv
import json
import logging
import os

from .storage_format import StorageFormat


class LocalDataStorage:
    """
    A class to handle the storage of scraped data locally in either JSON or CSV format.
    """

    def __init__(
        self, default_file_path: str = "scraped_data.csv", default_storage_format: StorageFormat = StorageFormat.CSV
    ):
        """
        Initialize LocalDataStorage.

        Args:
            default_file_path (str): Default file path to use if none is provided in `save_data`.
            default_storage_format (StorageFormat): Default file format to use if none is provided in StorageFormat.CSV.
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.default_file_path = default_file_path
        self.default_storage_format = default_storage_format

    def resolve_target_file_path(
        self, file_path: str | None, storage_format: StorageFormat | str | None
    ) -> tuple[str, str]:
        """
        Determine the final file path (with extension) and normalized format string.
        """
        target_file_path = file_path or self.default_file_path

        if isinstance(storage_format, StorageFormat):
            format_to_use = storage_format.value
        elif isinstance(storage_format, str):
            format_to_use = storage_format.lower()
        elif storage_format is None:
            format_to_use = self.default_storage_format.value
        else:
            raise ValueError("Unsupported storage_format type provided.")

        valid_formats = {f.value for f in StorageFormat}
        if format_to_use not in valid_formats:
            raise ValueError(
                f"Invalid storage format. Supported formats are: {', '.join(sorted(valid_formats))}."
            )

        if not target_file_path.endswith(f".{format_to_use}"):
            target_file_path = f"{target_file_path}.{format_to_use}"

        return target_file_path, format_to_use

    def save_data(
        self, data: dict | list[dict], file_path: str | None = None, storage_format: StorageFormat | str | None = None
    ):
        """
        Save scraped data to a local CSV file.

        Args:
            data (Union[Dict, List[Dict]]): The data to save, either as a dictionary or a list of dictionaries.
            file_path (str, optional): The file path to save the data. Defaults to `self.default_file_path`.
            storage_format (StorageFormat, optional): The format to save the data in ("csv" or "json").
            Defaults to `self.default_storage_format`.

        Raises:
            ValueError: If the data is not in the correct format (dict or list of dicts).
            Exception: If an error occurs during file operations.
        """
        if isinstance(data, dict):
            data = [data]

        if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
            raise ValueError("Data must be a dictionary or a list of dictionaries.")

        target_file_path, format_to_use = self.resolve_target_file_path(
            file_path=file_path, storage_format=storage_format
        )

        self._ensure_directory_exists(target_file_path)

        if format_to_use == StorageFormat.CSV.value:
            self._save_as_csv(data, target_file_path)
        elif format_to_use == StorageFormat.JSON.value:
            self._save_as_json(data, target_file_path)
        elif format_to_use == StorageFormat.JSONL.value:
            self._save_as_jsonl(data, target_file_path)
        else:
            raise ValueError("Unsupported file format.")

    def append_json_record(
        self, record: dict, file_path: str | None = None, storage_format: StorageFormat | str | None = None
    ):
        """Append a single record to a JSON file, creating it if necessary."""
        if not isinstance(record, dict):
            raise ValueError("Record must be a dictionary.")

        target_file_path, format_to_use = self.resolve_target_file_path(
            file_path=file_path, storage_format=storage_format
        )

        if format_to_use != StorageFormat.JSON.value:
            raise ValueError("append_json_record is only supported for JSON format.")

        self._ensure_directory_exists(target_file_path)
        self._save_as_json([record], target_file_path)

    def reset_json_file(
        self, file_path: str | None = None, storage_format: StorageFormat | str | None = None
    ) -> str:
        """Create or truncate the target JSON file to an empty array."""
        target_file_path, format_to_use = self.resolve_target_file_path(
            file_path=file_path, storage_format=storage_format
        )

        if format_to_use == StorageFormat.JSON.value:
            self._ensure_directory_exists(target_file_path)
            with open(target_file_path, "w", encoding="utf-8") as file:
                json.dump([], file, indent=4)
        elif format_to_use == StorageFormat.JSONL.value:
            # Truncate to empty file for JSONL
            self._ensure_directory_exists(target_file_path)
            with open(target_file_path, "w", encoding="utf-8") as file:
                file.write("")
        else:
            raise ValueError("reset_json_file is only supported for JSON/JSONL format.")

        return target_file_path

    def _save_as_csv(self, data: list[dict], file_path: str):
        """Save data in CSV format."""
        try:
            with open(file_path, mode="a", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=data[0].keys())

                # Write header only if the file is newly created
                if os.path.getsize(file_path) == 0:
                    writer.writeheader()

                writer.writerows(data)

            self.logger.info(f"Successfully saved {len(data)} record(s) to {file_path}")

        except Exception as e:
            self.logger.error(f"Error saving data to {file_path}: {e!s}", exc_info=True)
            raise

    def _save_as_jsonl(self, data: list[dict], file_path: str):
        """Save data in JSON Lines format (one JSON per line)."""
        try:
            with open(file_path, "a", encoding="utf-8") as file:
                for item in data:
                    file.write(json.dumps(item, ensure_ascii=False) + "\n")
            self.logger.info(f"Successfully appended {len(data)} JSONL line(s) to {file_path}")
        except Exception as e:
            self.logger.error(f"Error appending JSONL to {file_path}: {e!s}", exc_info=True)
            raise

    def append_jsonl_record(
        self, record: dict, file_path: str | None = None, storage_format: StorageFormat | str | None = None
    ):
        """Append a single record as a JSONL line."""
        if not isinstance(record, dict):
            raise ValueError("Record must be a dictionary.")
        target_file_path, format_to_use = self.resolve_target_file_path(
            file_path=file_path, storage_format=storage_format
        )
        if format_to_use != StorageFormat.JSONL.value:
            raise ValueError("append_jsonl_record is only supported for JSONL format.")
        self._ensure_directory_exists(target_file_path)
        self._save_as_jsonl([record], target_file_path)

    def _save_as_json(self, data: list[dict], file_path: str):
        """Save data in JSON format."""
        try:
            # Load existing data if the file already exists
            existing_data = []

            if os.path.exists(file_path):
                with open(file_path, encoding="utf-8") as file:
                    try:
                        existing_data = json.load(file)
                    except json.JSONDecodeError:
                        self.logger.warning(f"File {file_path} exists but is empty or invalid JSON.")

            combined_data = existing_data + data

            with open(file_path, "w", encoding="utf-8") as file:
                json.dump(combined_data, file, indent=4)

            self.logger.info(f"Successfully saved {len(data)} record(s) to {file_path}")

        except Exception as e:
            self.logger.error(f"Error saving data to {file_path}: {e!s}", exc_info=True)
            raise

    def _ensure_directory_exists(self, file_path: str):
        """Ensures the directory for the given file path exists. If it doesn't exist, creates it."""
        directory = os.path.dirname(file_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory)
