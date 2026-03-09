"""
Structured reporting (JSON, CSV, HTML) for tools output.
"""

import csv
import json
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class Reporter(ABC):
    """Base reporter interface."""

    @abstractmethod
    def write(self, data: Any, output_path: Path) -> None:
        """Write data to output file."""

        pass


class JSONReporter(Reporter):
    """JSON format reporter."""

    def format(self, data: Any, pretty: bool = True) -> str:
        """Format data as JSON string for console output."""
        return json.dumps(data, indent=2 if pretty else None, default=str)

    def write(
        self, data: Any, output_path: Path, pretty: bool = True
    ) -> None:
        """Write data as JSON.

        Args:
            data: Data to write
            output_path: Output file path
            pretty: Pretty print JSON
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write(self.format(data, pretty=pretty))


class CSVReporter(Reporter):
    """CSV format reporter."""

    def write(
        self,
        data: List[Dict[str, Any]],
        output_path: Path,
        fieldnames: Optional[List[str]] = None,
    ) -> None:
        """Write data as CSV.

        Args:
            data: List of dictionaries to write
            output_path: Output file path
            fieldnames: CSV column names (auto-detected if None)
        """
        if not data:
            return

        if fieldnames is None:
            fieldnames = list(data[0].keys())

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)


class HTMLReporter(Reporter):
    """HTML format reporter."""

    def write(
        self, title: str, data: List[Dict[str, Any]], output_path: Path
    ) -> None:
        """Write data as HTML table.

        Args:
            title: HTML page title
            data: List of dictionaries to render
            output_path: Output file path
        """
        if not data:
            return

        fieldnames = list(data[0].keys())
        output_path.parent.mkdir(parents=True, exist_ok=True)

        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>{title}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #4CAF50; color: white; }}
        tr:nth-child(even) {{ background-color: #f2f2f2; }}
        .success {{ color: green; }}
        .error {{ color: red; }}
        .warning {{ color: orange; }}
    </style>
</head>
<body>
    <h1>{title}</h1>
    <p>Generated: {datetime.now().isoformat()}</p>
    <table>
        <tr>
            {''.join(f'<th>{name}</th>' for name in fieldnames)}
        </tr>
"""
        for row in data:
            html += "        <tr>\n"
            for field in fieldnames:
                value = row.get(field, "")
                html += f"            <td>{value}</td>\n"
            html += "        </tr>\n"

        html += """    </table>
</body>
</html>"""

        with open(output_path, "w") as f:
            f.write(html)
