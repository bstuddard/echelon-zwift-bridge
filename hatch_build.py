"""Carry an available Vue build through both source and wheel distributions."""
from pathlib import Path
from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        frontend = Path(self.root) / "backend" / "frontend_dist"
        if frontend.is_dir():
            destinations = {
                "sdist": "backend/frontend_dist",
                "wheel": "echelon_bridge/frontend_dist",
            }
            if self.target_name in destinations:
                build_data["force_include"][str(frontend)] = destinations[self.target_name]
