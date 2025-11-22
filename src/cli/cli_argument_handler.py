import logging
import csv
from pathlib import Path

from src.cli.cli_argument_parser import CLIArgumentParser
from src.cli.cli_argument_validator import CLIArgumentValidator


class CLIArgumentHandler:
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.parser = CLIArgumentParser().get_parser()
        self.validator = CLIArgumentValidator()

    def parse_and_validate_args(self) -> dict:
        """Parses and validates command-line arguments, returning a structured dictionary."""
        args = self.parser.parse_args()

        # Allow --match_links to accept a single CSV file path. If provided, load links from CSV.
        try:
            if getattr(args, "match_links", None):
                # If user passed a single token and it's a path to an existing file, read it as CSV
                if isinstance(args.match_links, list) and len(args.match_links) == 1:
                    potential_path = Path(args.match_links[0])
                    if potential_path.exists() and potential_path.is_file():
                        loaded_links: list[str] = []
                        with potential_path.open("r", encoding="utf-8", newline="") as f:
                            sample = f.read(2048)
                            f.seek(0)
                            # Try DictReader first to honor headers
                            try:
                                reader = csv.DictReader(f)
                                if reader.fieldnames:
                                    header_lower = [h.strip().lower() for h in reader.fieldnames if h]
                                    key = "match_link" if "match_link" in header_lower else reader.fieldnames[0]
                                    f.seek(0)
                                    reader = csv.DictReader(f)
                                    for row in reader:
                                        val = (row.get(key) or "").strip()
                                        if val:
                                            loaded_links.append(val)
                                else:
                                    # Fall back to simple CSV reader
                                    f.seek(0)
                                    reader2 = csv.reader(f)
                                    for row in reader2:
                                        if row and row[0].strip():
                                            loaded_links.append(row[0].strip())
                            except Exception:
                                # Fallback to simple reader if DictReader fails
                                f.seek(0)
                                reader2 = csv.reader(f)
                                for row in reader2:
                                    if row and row[0].strip():
                                        loaded_links.append(row[0].strip())

                        # Replace args.match_links with the loaded list
                        args.match_links = loaded_links
                        self.logger.info(
                            "Loaded %s match links from CSV: %s", len(loaded_links), potential_path
                        )
        except Exception as e:
            self.logger.error("Failed to load match links from CSV: %s", e, exc_info=True)

        if not args.command:
            self.logger.error("No CLI args Command provided")
            self.parser.print_help()
            exit(1)

        try:
            self.validator.validate_args(args)
        except ValueError as e:
            self.logger.error(f"CLI args validation failed: {e}")
            self.parser.print_help()
            exit(1)

        # Normalize 'current' to None for allowed sports so URL builder targets current season
        if (
            args.command == "scrape_historic"
            and isinstance(args.season, str)
            and args.season.lower() == "current"
            and isinstance(args.sport, str)
            and args.sport.lower()
            in {
                "tennis",
                "football",
                "baseball",
                "ice-hockey",
                "rugby-league",
                "rugby-union",
            }
        ):
            args.season = None

        return {
            "command": args.command,
            "match_links": getattr(args, "match_links", None),
            "sport": getattr(args, "sport", None),
            "date": getattr(args, "date", None),
            "leagues": getattr(args, "leagues", None),
            "season": getattr(args, "season", None),
            "storage_type": args.storage,
            "storage_format": getattr(args, "format", None),
            "file_path": getattr(args, "file_path", None),
            "max_pages": getattr(args, "max_pages", None),
            "proxies": getattr(args, "proxies", None),
            "headless": args.headless,
            "markets": args.markets,
            "browser_user_agent": getattr(args, "browser_user_agent", None),
            "browser_locale_timezone": getattr(args, "browser_locale_timezone", None),
            "browser_timezone_id": getattr(args, "browser_timezone_id", None),
            "target_bookmaker": getattr(args, "target_bookmaker", None),
            "scrape_odds_history": getattr(args, "scrape_odds_history", False),
            "preview_submarkets_only": getattr(args, "preview_submarkets_only", False),
            "concurrency_tasks": getattr(args, "concurrency_tasks", None),
        }
