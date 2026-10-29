"""Bundle the Vue production build when available; allow API-only installs."""
from pathlib import Path
from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        frontend = Path(self.root) / "backend" / "frontend_dist"
        if self.target_name == "wheel" and frontend.is_dir():
            build_data["force_include"][str(frontend)] = "echelon_bridge/frontend_dist"
