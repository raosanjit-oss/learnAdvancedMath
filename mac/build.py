"""Build with a conda-packed Apple Silicon manim_env archive as the argument."""

import hashlib
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile

here = Path(__file__).resolve().parent
archive = Path(sys.argv[1]).resolve(strict=True)
destination = here.parent / "dist"
stage = tempfile.TemporaryDirectory(prefix="visual-math-build-")
app = Path(stage.name) / "Visual Math.app"
resources = app / "Contents/Resources"
executable = app / "Contents/MacOS/VisualMath"
resources.mkdir(parents=True, exist_ok=True)
executable.parent.mkdir(exist_ok=True)

subprocess.run(["swiftc", "-parse-as-library", "-O", "-target", "arm64-apple-macos13.0",
                "-module-cache-path", str(destination / "module-cache"),
                str(here / "VisualMath.swift"), str(here / "LessonForm.swift"), "-o", str(executable)], check=True)
for path in [here / "run.sh", here / "Slope.visualmath", here / "render_document.py", here.parent / "lesson_tools.py"]:
    shutil.copyfile(path, resources / path.name)
shutil.copyfile(archive, resources / "runtime.tar.gz")
with archive.open("rb") as file:
    version = hashlib.file_digest(file, "sha256").hexdigest()[:16]
(resources / "runtime-version").write_text("manim-" + version)
info = {
    "CFBundleIdentifier": "org.visualmath.desktop", "CFBundleName": "Visual Math",
    "CFBundlePackageType": "APPL", "CFBundleExecutable": executable.name,
    "CFBundleVersion": "1", "CFBundleShortVersionString": "0.1", "LSMinimumSystemVersion": "13.0",
    "NSHighResolutionCapable": True, "CFBundleDocumentTypes": [{
        "CFBundleTypeName": "Visual Math Lesson", "CFBundleTypeRole": "Viewer",
        "LSItemContentTypes": ["org.visualmath.lesson"]}],
    "UTExportedTypeDeclarations": [{"UTTypeIdentifier": "org.visualmath.lesson",
        "UTTypeConformsTo": ["public.json"], "UTTypeDescription": "Visual Math lesson",
        "UTTypeTagSpecification": {"public.filename-extension": ["visualmath"]}}],
}
(app / "Contents/Info.plist").write_bytes(plistlib.dumps(info))
subprocess.run(["codesign", "--force", "--sign", "-", str(app)], check=True)
subprocess.run(["codesign", "--verify", "--strict", str(app)], check=True)
subprocess.run(["ditto", "-c", "-k", "--keepParent", str(app), str(destination / "Visual-Math-Mac.zip")], check=True)
subprocess.run(["ditto", str(app), str(destination / app.name)], check=True)
print(destination / "Visual-Math-Mac.zip")
