# run_files.py
"""
Centralized management of run artifact file names and paths.
"""
from __future__ import annotations
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

class RunFiles:
    """
    A class to manage all run artifact file names and paths consistently.
    
    This class centralizes all file naming conventions used in the fedrate project,
    making it easier to maintain and modify file names in one place.
    """
    
    def __init__(self, run_id: str, art_dir: Path):
        self.run_id = run_id
        self.art_dir = art_dir
    
    # Manifest file
    def manifest(self) -> Path:
        """Run metadata manifest file."""
        return self.art_dir / f"{self.run_id}.manifest.json"
    
    # Source files
    def sources_final(self) -> Path:
        """Final source records in JSONL format."""
        return self.art_dir / f"{self.run_id}.sources.final.jsonl"
    
    def sources_raw(self) -> Path:
        """Raw source data."""
        return self.art_dir / f"{self.run_id}.sources.raw.json"
    
    # Macro Analyst files
    def macro_analyst_llm(self, timestamp: int | None = None) -> Path:
        """LLM calls from MacroAnalyst."""
        if timestamp is None:
            timestamp = int(time.time())
        return self.art_dir / f"{self.run_id}.MacroAnalyst.{timestamp}.llm.json"
    
    def macro_notes(self) -> Path:
        """Notes from MacroAnalyst."""
        return self.art_dir / f"{self.run_id}.macro.notes.md"
    
    # Fact Checker files
    def factcheck(self) -> Path:
        """Fact check results."""
        return self.art_dir / f"{self.run_id}.factcheck.json"
    
    # Executive Writer files
    def executive_writer_llm(self, timestamp: int | None = None) -> Path:
        """LLM calls from ExecutiveWriter."""
        if timestamp is None:
            timestamp = int(time.time())
        return self.art_dir / f"{self.run_id}.ExecutiveWriter.{timestamp}.llm.json"
    
    def brief(self) -> Path:
        """Final executive brief."""
        return self.art_dir / f"{self.run_id}.brief.md"
    
    # Debug file
    def debug(self) -> Path:
        """Debug information."""
        return self.art_dir / f"{self.run_id}.debug.json"
