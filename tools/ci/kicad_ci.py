#!/usr/bin/env python3
"""CI helpers for the KiCad projects in this repo.

Subcommands:
  projects   List KiCad projects as a JSON matrix for GitHub Actions.
  setup      Write global KiCad library tables (stock + external libraries).
  hygiene    Check tracked files for junk and for the expected KiCad version.
  check      Run ERC, DRC (with schematic parity) and library checks on a project.
  outputs    Generate fabrication/documentation outputs for a project.
  diff       Render visual schematic/PCB diffs between a base commit and HEAD.

Everything is driven by hdw/ci-config.json. Run with --help for options.
"""

import argparse
import fnmatch
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath

REPO = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO / "hdw" / "ci-config.json"
KICAD_CLI = os.environ.get("KICAD_CLI", "kicad-cli")
MODES = ("enforce", "report", "off")

# Violation types that mean a library (or a part in it) can't be found.
LIB_TYPES = {"lib_symbol_issues", "footprint_link_issues", "lib_footprint_issues"}
# "Copy in design differs from library" - worth knowing, never fatal.
MISMATCH_TYPES = {"lib_symbol_mismatch", "lib_footprint_mismatch"}

# Files that should never be committed (matched against each path component
# and against the full repo-relative path).
FORBIDDEN_PATTERNS = [
    "*-backups", "_autosave-*", "#auto_saved_files#", "*.lck", "~*.lck",
    "fp-info-cache", "*.kicad_prl", "*.bak", "*.bck", "*-bak", "*.kicad_sch-bak",
    "*.kicad_pcb-bak", "*.sch-bak", ".history",
    "*.rpt", "*-drc.json", "*-erc.json", "*.net", "*.dsn", "*.ses",
    "*.gbr", "*.gbrjob", "*.drl", "*.gtl", "*.gbl", "*.gto", "*.gbo", "*.gts",
    "*.gbs", "*.gtp", "*.gbp", "*.gm1", "*.gko", "*.g[0-9]", "*.g[0-9][0-9]",
]
# Outputs KiCad writes next to the project as <project>.<ext>; CI builds these.
GENERATED_PROJECT_EXTS = [".pdf", ".step", ".stp", ".wrl", "-pos.csv", ".csv", ".ipc", ".d356"]
VERSIONED_EXTS = {".kicad_sch", ".kicad_pcb", ".kicad_sym", ".kicad_mod"}


# --------------------------------------------------------------------------- helpers

def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def rel(path):
    """Repo-relative POSIX path string."""
    return Path(path).resolve().relative_to(REPO).as_posix()


def gh_annotation(level, message, file=None, title=None):
    """Emit a GitHub Actions workflow command (plain text when run locally)."""
    message = message.replace("%", "%25").replace("\r", "").replace("\n", "%0A")
    props = []
    if file:
        props.append(f"file={file}")
    if title:
        props.append(f"title={title.replace(',', ';').replace(':', ';')}")
    print(f"::{level} {','.join(props)}::{message}" if props else f"::{level}::{message}")


def append_summary(markdown):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(markdown + "\n")


def set_output(name, value):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{name}={value}\n")
    else:
        print(f"{name}={value}")


def kicad(*args, cwd=None, fatal=True):
    cmd = [KICAD_CLI, *map(str, args)]
    print("$ " + " ".join(f'"{a}"' if " " in a else a for a in cmd), flush=True)
    result = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    out = (result.stdout + result.stderr).strip()
    if out:
        print(out, flush=True)
    if result.returncode != 0 and fatal:
        raise RuntimeError(f"kicad-cli exited with {result.returncode}: {' '.join(cmd)}")
    return result.returncode == 0


def git(*args, cwd=REPO):
    return subprocess.run(["git", *args], cwd=cwd, check=True, text=True,
                          capture_output=True).stdout


def find_projects(root=REPO, config=None):
    config = config or load_config()
    projects = []
    for proj_root in config.get("project_roots", ["hdw"]):
        for pro in sorted((root / proj_root).rglob("*.kicad_pro")):
            parts = pro.relative_to(root).parts
            if any(p.endswith("-backups") or p.startswith(".") for p in parts):
                continue
            d = pro.parent.relative_to(root).as_posix()
            projects.append({
                "dir": d,
                "name": pro.stem,
                "slug": "-".join(PurePosixPath(d).parts[1:]) or pro.stem,
            })
    return projects


def project_modes(config, project_dir):
    modes = {"erc": "enforce", "drc": "enforce", "libraries": "enforce"}
    modes.update(config.get("defaults", {}))
    modes.update(config.get("projects", {}).get(project_dir, {}))
    for key, value in modes.items():
        if value not in MODES:
            raise SystemExit(f"ci-config.json: {project_dir}: {key} must be one of {MODES}, got {value!r}")
    return modes


def board_layers(pcb_path):
    """(copper layers in stack order, all layer names) from a .kicad_pcb."""
    text = Path(pcb_path).read_text(encoding="utf-8", errors="replace")
    m = re.search(r"\(layers\b(.*?)\n\s*\)", text, re.S)
    if not m:
        return ["F.Cu", "B.Cu"], set()
    entries = re.findall(r'\(\d+\s+"([^"]+)"\s+(\w+)', m.group(1))
    names = {n for n, _ in entries}
    copper = [n for n, kind in entries if n.endswith(".Cu")]
    inner = sorted((n for n in copper if n.startswith("In")), key=lambda n: int(re.sub(r"\D", "", n)))
    copper = [n for n in ("F.Cu",) if n in copper] + inner + [n for n in ("B.Cu",) if n in copper]
    return copper or ["F.Cu", "B.Cu"], names


# --------------------------------------------------------------------------- projects

def cmd_projects(args):
    projects = find_projects()
    set_output("matrix", json.dumps({"include": projects}))
    set_output("count", str(len(projects)))
    for p in projects:
        print(f"  {p['dir']}  ({p['name']})", file=sys.stderr)


# --------------------------------------------------------------------------- setup

def kicad_config_dir(version):
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(base) / "kicad" / version


def cmd_setup(args):
    config = load_config()
    template_dir = Path(os.environ.get("KICAD_TEMPLATE_DIR", "/usr/share/kicad/template"))
    cfg_dir = kicad_config_dir(config["kicad_version"])
    cfg_dir.mkdir(parents=True, exist_ok=True)
    libs_dir = Path(args.libs_dir).resolve()
    libs_dir.mkdir(parents=True, exist_ok=True)

    extra = {"sym": [], "fp": []}
    for lib in config.get("external_libraries", []):
        name = Path(lib["repo"].rstrip("/")).stem
        dest = libs_dir / name
        if not dest.exists():
            clone = ["git", "clone", "--depth", "1"]
            if lib.get("ref"):
                clone += ["--branch", lib["ref"]]
            subprocess.run(clone + [lib["repo"], str(dest)], check=True)
        sha = git("rev-parse", "HEAD", cwd=dest).strip()
        print(f"External library {lib['repo']} @ {sha}")
        for kind, key in (("sym", "symbol_libs"), ("fp", "footprint_libs")):
            for nick, path in lib.get(key, {}).items():
                full = dest / path
                if not full.exists():
                    raise SystemExit(f"{lib['repo']}: {path} not found (library '{nick}')")
                extra[kind].append((nick, full.as_posix()))

    for kind in ("sym", "fp"):
        template = (template_dir / f"{kind}-lib-table").read_text(encoding="utf-8").rstrip()
        if not template.endswith(")"):
            raise SystemExit(f"Unexpected format in {template_dir}/{kind}-lib-table")
        entries = "".join(
            f'\n  (lib (name "{nick}")(type "KiCad")(uri "{uri}")(options "")(descr "CI external library"))'
            for nick, uri in extra[kind])
        (cfg_dir / f"{kind}-lib-table").write_text(template[:-1] + entries + "\n)\n", encoding="utf-8")
        print(f"Wrote {cfg_dir / f'{kind}-lib-table'} (+{len(extra[kind])} external)")


# --------------------------------------------------------------------------- hygiene

def cmd_hygiene(args):
    config = load_config()
    want = config["kicad_version"]
    tracked = [p for p in git("ls-files", "-z").split("\0") if p]
    project_stems = {(str(PurePosixPath(p).parent), PurePosixPath(p).stem)
                     for p in tracked if p.endswith(".kicad_pro")}
    roots = tuple(r.rstrip("/") + "/" for r in config.get("project_roots", ["hdw"]))
    problems = []

    for path in tracked:
        pp = PurePosixPath(path)
        hit = next((pat for pat in FORBIDDEN_PATTERNS
                    if any(fnmatch.fnmatch(part, pat) for part in pp.parts)), None)
        if hit:
            problems.append((path, f"should not be committed (matches '{hit}')"))
            continue
        for ext in GENERATED_PROJECT_EXTS:
            if pp.name.endswith(ext) and (str(pp.parent), pp.name[: -len(ext)]) in project_stems:
                problems.append((path, "generated output next to the project; CI builds this - "
                                       "remove it with 'git rm --cached'"))
                break
        if pp.suffix in VERSIONED_EXTS and path.startswith(roots):
            head = (REPO / path).read_text(encoding="utf-8", errors="replace")[:4096]
            m = re.search(r'\(generator_version\s+"([^"]+)"\)', head)
            found = m.group(1) if m else "unknown (pre-KiCad 7 format)"
            if found != want:
                problems.append((path, f"saved by KiCad {found}; this repo expects KiCad {want}. "
                                       f"Open and re-save it in KiCad {want}."))

    lines = ["## Repository hygiene", ""]
    if problems:
        lines += ["| File | Problem |", "|---|---|"]
        for path, msg in problems:
            gh_annotation("error", msg, file=path, title="Hygiene")
            lines.append(f"| `{path}` | {msg} |")
    else:
        lines.append(f"All {len(tracked)} tracked files OK (KiCad {want}, no backups/generated outputs).")
    append_summary("\n".join(lines))
    print("\n".join(lines))
    return 1 if problems else 0


# --------------------------------------------------------------------------- check

def parse_lib_table(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    return re.findall(r'\(lib\s+\(name\s+"([^"]*)"\).*?\(uri\s+"([^"]*)"\)', text, re.S)


def check_lib_tables(proj_dir):
    """Static check of project lib tables: portable paths that exist in the repo."""
    findings = []
    for table in ("sym-lib-table", "fp-lib-table"):
        path = proj_dir / table
        if not path.exists():
            continue
        for nick, uri in parse_lib_table(path):
            where = f"{table}: library '{nick}'"
            if re.match(r"^([A-Za-z]:[\\/]|/|\\\\)", uri):
                findings.append((rel(path), f"{where} uses an absolute path ({uri}). "
                                            "Use ${KIPRJMOD}/relative/path so it works on other machines."))
            elif "${KIPRJMOD}" in uri:
                target = Path(uri.replace("${KIPRJMOD}", str(proj_dir))).resolve()
                if not target.exists():
                    findings.append((rel(path), f"{where} points to {uri}, which is not in the repo."))
                elif REPO not in target.parents:
                    findings.append((rel(path), f"{where} points outside the repo ({uri})."))
    return findings


def collect_violations(report, source):
    items = []
    for sheet in report.get("sheets", []):
        for v in sheet.get("violations", []):
            items.append({**v, "source": source, "sheet": sheet.get("path", "/")})
    for key in ("violations", "unconnected_items", "schematic_parity"):
        for v in report.get(key, []):
            items.append({**v, "source": source, "group": key})
    return items


def classify(v, modes):
    """Return (check, fails) for a single violation."""
    if v["type"] in LIB_TYPES:
        return "libraries", modes["libraries"] == "enforce"
    if v["type"] in MISMATCH_TYPES:
        return v["source"], False
    if v.get("group") == "schematic_parity":
        return "drc", modes["drc"] == "enforce"
    return v["source"], v["severity"] == "error" and modes[v["source"]] == "enforce"


def cmd_check(args):
    config = load_config()
    proj_dir = (REPO / args.project).resolve()
    proj_rel = rel(proj_dir)
    pro = next(proj_dir.glob("*.kicad_pro"))
    name = pro.stem
    sch, pcb = proj_dir / f"{name}.kicad_sch", proj_dir / f"{name}.kicad_pcb"
    modes = project_modes(config, proj_rel)
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    results = []  # dicts: check, severity, type, description, items, file, fails
    for path, msg in (check_lib_tables(proj_dir) if modes["libraries"] != "off" else []):
        results.append({"check": "libraries", "severity": "error", "type": "lib_table",
                        "description": msg, "items": [], "file": path,
                        "fails": modes["libraries"] == "enforce"})

    runs = []
    if modes["erc"] != "off" or modes["libraries"] != "off":
        runs.append(("erc", sch, ["sch", "erc"]))
    if modes["drc"] != "off" or modes["libraries"] != "off":
        if pcb.exists():
            runs.append(("drc", pcb, ["pcb", "drc", "--schematic-parity"]))
    for source, target, cmd in runs:
        report_path = out / f"{name}-{source}.json"
        kicad(*cmd, "--format", "json", "--severity-all", "--units", "mm",
              "-o", report_path, target, cwd=proj_dir)
        kicad(*cmd, "--format", "report", "--severity-all", "--units", "mm",
              "-o", out / f"{name}-{source}.rpt", target, cwd=proj_dir, fatal=False)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        for v in collect_violations(report, source):
            check, fails = classify(v, modes)
            if modes[check] == "off":
                continue
            results.append({"check": check, "severity": v["severity"], "type": v["type"],
                            "description": v["description"],
                            "items": [i.get("description", "") for i in v.get("items", [])],
                            "file": rel(target), "fails": fails})

    # Annotations: one per (check, type) so the PR view stays readable.
    groups = {}
    for r in results:
        groups.setdefault((r["check"], r["type"], r["file"]), []).append(r)
    for (check, vtype, file), rs in sorted(groups.items()):
        fails = any(r["fails"] for r in rs)
        level = "error" if fails else ("warning" if any(r["severity"] == "error" for r in rs) else "notice")
        detail = "\n".join(f"- {r['description']}" + (f" ({'; '.join(r['items'])})" if r["items"] else "")
                           for r in rs[:8])
        more = f"\n...and {len(rs) - 8} more" if len(rs) > 8 else ""
        gh_annotation(level, f"{len(rs)}x {vtype}\n{detail}{more}", file=file,
                      title=f"{name} {check.upper()} {vtype}")

    # Summary
    lines = [f"## {name}", f"`{proj_rel}`", "", "| Check | Mode | Errors | Warnings | Result |",
             "|---|---|---|---|---|"]
    failed_checks = []
    for check in ("libraries", "erc", "drc"):
        rs = [r for r in results if r["check"] == check]
        errors = sum(r["severity"] == "error" for r in rs)
        warnings = len(rs) - errors
        fails = any(r["fails"] for r in rs)
        if modes[check] == "off":
            status = "skipped"
        elif fails:
            status, _ = "❌ fail", failed_checks.append(check)
        elif rs:
            status = "⚠️ issues (report-only)" if modes[check] == "report" else "✅ pass (warnings)"
        else:
            status = "✅ pass"
        lines.append(f"| {check.upper() if check != 'libraries' else 'Libraries'} | {modes[check]} "
                     f"| {errors} | {warnings} | {status} |")
    if results:
        lines += ["", "<details><summary>Violations by type</summary>", "",
                  "| Check | Type | Severity | Count | Example |", "|---|---|---|---|---|"]
        counts = Counter((r["check"], r["type"], r["severity"]) for r in results)
        for (check, vtype, sev), n in sorted(counts.items()):
            ex = next(r for r in results if (r["check"], r["type"], r["severity"]) == (check, vtype, sev))
            desc = ex["description"] + (f" ({ex['items'][0]})" if ex["items"] else "")
            lines.append(f"| {check} | `{vtype}` | {sev} | {n} | {desc.replace('|', '/')} |")
        lines += ["", "</details>"]
    lines.append("")
    summary = "\n".join(lines)
    (out / f"{name}-summary.md").write_text(summary, encoding="utf-8")
    append_summary(summary)
    print(summary)
    if failed_checks:
        print(f"FAILED: {', '.join(failed_checks)} (enforced in hdw/ci-config.json)")
        return 1
    return 0


# --------------------------------------------------------------------------- outputs

def zip_dir(src, dest):
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(Path(src).rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(src).as_posix())


def cmd_outputs(args):
    config = load_config()
    proj_dir = (REPO / args.project).resolve()
    name = next(proj_dir.glob("*.kicad_pro")).stem
    sch, pcb = proj_dir / f"{name}.kicad_sch", proj_dir / f"{name}.kicad_pcb"
    out = Path(args.out).resolve()
    if out.exists():
        shutil.rmtree(out)
    fab, asm, docs, mech = out / "fab", out / "assembly", out / "docs", out / "3d"
    for d in (fab / "gerbers", asm, docs, mech):
        d.mkdir(parents=True, exist_ok=True)
    tag = args.label or "local"
    warnings = []

    def optional(label, *cmd):
        try:
            if not kicad(*cmd, cwd=proj_dir, fatal=False):
                warnings.append(label)
        except OSError as e:
            warnings.append(f"{label} ({e})")

    # Documentation
    kicad("sch", "export", "pdf", "-o", docs / f"{name}-schematic.pdf", sch, cwd=proj_dir)
    copper, names = board_layers(pcb)
    doc_layers = copper + [l for l in ("F.Silkscreen", "B.Silkscreen", "F.Fab", "B.Fab")
                           if not names or l in names]
    optional("PCB PDF", "pcb", "export", "pdf", "--mode-multipage", "--ibt",
             "--layers", ",".join(doc_layers), "--common-layers", "Edge.Cuts",
             "-o", docs / f"{name}-pcb.pdf", pcb)

    # Fabrication
    kicad("pcb", "export", "gerbers", "--board-plot-params", "-o", f"{fab / 'gerbers'}/", pcb, cwd=proj_dir)
    kicad("pcb", "export", "drill", "--generate-map", "--map-format", "gerberx2",
          "-o", f"{fab / 'gerbers'}/", pcb, cwd=proj_dir)
    optional("IPC-D-356 netlist", "pcb", "export", "ipcd356", "-o", fab / f"{name}.d356", pcb)
    zip_dir(fab / "gerbers", fab / f"{name}-gerbers-{tag}.zip")

    # Assembly
    kicad("pcb", "export", "pos", "--format", "csv", "--units", "mm", "--side", "both",
          "--exclude-dnp", "-o", asm / f"{name}-pos.csv", pcb, cwd=proj_dir)
    bom = config.get("bom", {})
    bom_args = []
    for key, flag in (("fields", "--fields"), ("labels", "--labels"), ("group_by", "--group-by")):
        if bom.get(key):
            bom_args += [flag, bom[key]]
    kicad("sch", "export", "bom", *bom_args, "-o", asm / f"{name}-bom.csv", sch, cwd=proj_dir)

    # 3D (needs 3D models / an OpenGL-capable environment; never fatal)
    if not args.no_3d:
        optional("STEP model", "pcb", "export", "step", "--subst-models", "--no-dnp", "-f",
                 "-o", mech / f"{name}.step", pcb)
        for side in ("top", "bottom"):
            optional(f"{side} render", "pcb", "render", "--side", side, "--quality", "high",
                     "--width", "1600", "--height", "1200", "-o", mech / f"{name}-{side}.png", pcb)

    sha = os.environ.get("GITHUB_SHA") or git("rev-parse", "HEAD").strip()
    (out / "BUILD_INFO.txt").write_text(
        f"project: {rel(proj_dir)}\ncommit: {sha}\nlabel: {tag}\n"
        f"kicad: {subprocess.run([KICAD_CLI, 'version'], capture_output=True, text=True).stdout.strip()}\n"
        + (f"skipped/failed optional outputs: {', '.join(warnings)}\n" if warnings else ""),
        encoding="utf-8")
    for w in warnings:
        gh_annotation("warning", f"Optional output failed: {w}", file=rel(pcb), title=f"{name} outputs")

    listing = sorted(f.relative_to(out).as_posix() for f in out.rglob("*") if f.is_file())
    append_summary(f"### {name} outputs\n\n" + "\n".join(f"- `{f}`" for f in listing
                                                          if not f.startswith("fab/gerbers/")) + "\n")
    print("\n".join(listing))


# --------------------------------------------------------------------------- diff

def svg_exports(proj_dir, name, dest, layers):
    """Export schematic pages and PCB layers as SVG into dest; returns {key: svg}."""
    files = {}
    sch, pcb = proj_dir / f"{name}.kicad_sch", proj_dir / f"{name}.kicad_pcb"
    if sch.exists():
        d = dest / "sch"
        d.mkdir(parents=True, exist_ok=True)
        kicad("sch", "export", "svg", "-b", "-n", "-o", d, sch, cwd=proj_dir, fatal=False)
        for f in d.glob("*.svg"):
            files[f"schematic/{f.stem}"] = f
    if pcb.exists():
        d = dest / "pcb"
        d.mkdir(parents=True, exist_ok=True)
        for layer in layers:
            f = d / f"{layer}.svg"
            ok = kicad("pcb", "export", "svg", "--mode-single", "--black-and-white",
                       "--exclude-drawing-sheet", "--page-size-mode", "2",
                       "--layers", layer, "--common-layers", "Edge.Cuts",
                       "-o", f, pcb, cwd=proj_dir, fatal=False)
            if ok and f.exists():
                files[f"pcb/{layer}"] = f
    return files


def magick(*args):
    return subprocess.run(["magick", *map(str, args)], text=True, capture_output=True)


def raster(svg, png):
    if svg is None:
        return None
    subprocess.run(["rsvg-convert", "--dpi-x", "150", "--dpi-y", "150", "-b", "white",
                    "-o", str(png), str(svg)], check=True)
    return png


def image_size(png):
    w, h = magick("identify", "-format", "%w %h", png).stdout.split()
    return int(w), int(h)


def make_diff(old_svg, new_svg, work, key):
    """Rasterise both sides; return (changed_pixels, old_png, new_png, diff_png)."""
    stem = key.replace("/", "__")
    old_png = raster(old_svg, work / f"{stem}.old.png")
    new_png = raster(new_svg, work / f"{stem}.new.png")
    ref = new_png or old_png
    w, h = image_size(ref)
    if old_png and new_png:
        w2, h2 = image_size(old_png)
        w, h = max(w, w2), max(h, h2)
    grays = {}
    for side, png in (("old", old_png), ("new", new_png)):
        g = work / f"{stem}.{side}.gray.png"
        if png:
            magick(png, "-background", "white", "-flatten", "-gravity", "northwest",
                   "-extent", f"{w}x{h}", "-colorspace", "Gray", g)
        else:
            magick("-size", f"{w}x{h}", "xc:white", "-colorspace", "Gray", g)
        grays[side] = g
    cmp = magick("compare", "-metric", "AE", "-fuzz", "10%", grays["old"], grays["new"], "null:")
    changed = int(float(re.split(r"\s", (cmp.stdout + cmp.stderr).strip())[0] or 0))
    diff_png = work / f"{stem}.diff.png"
    if changed:
        # R = new, G = old, B = both -> removed shows red, added shows green, unchanged black.
        magick(grays["new"], grays["old"], "(", grays["old"], grays["new"], "-compose", "darken",
               "-composite", ")", "-set", "colorspace", "sRGB", "-combine", diff_png)
    return changed, old_png, new_png, diff_png if changed else None


def cmd_diff(args):
    out = Path(args.out).resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    base = args.base
    changed_files = git("diff", "--name-only", f"{base}...HEAD").split()
    if not changed_files:
        changed_files = git("diff", "--name-only", base, "HEAD").split()

    tmp = Path(tempfile.mkdtemp(prefix="kicad-diff-"))
    base_tree = tmp / "base"
    git("worktree", "add", "--detach", str(base_tree), base)
    try:
        head_projects = {p["dir"]: p for p in find_projects(REPO)}
        base_projects = {p["dir"]: p for p in find_projects(base_tree)}
        all_dirs = sorted(set(head_projects) | set(base_projects))
        touched = [d for d in all_dirs
                   if any(f.startswith(d + "/") and f.endswith((".kicad_sch", ".kicad_pcb"))
                          for f in changed_files)]
        report = []  # (project, key, changed, rel paths)
        for d in touched:
            p = head_projects.get(d) or base_projects[d]
            name = p["name"]
            sides = {"old": base_tree / d, "new": REPO / d}
            layers = []
            for side_dir in sides.values():
                pcb = side_dir / f"{name}.kicad_pcb"
                if pcb.exists():
                    copper, names = board_layers(pcb)
                    for l in copper + [l for l in ("F.Silkscreen", "B.Silkscreen", "F.Fab", "B.Fab",
                                                   "F.Mask", "B.Mask") if not names or l in names]:
                        if l not in layers:
                            layers.append(l)
            svgs = {side: (svg_exports(side_dir, name, tmp / p["slug"] / side, layers)
                           if side_dir.exists() else {}) for side, side_dir in sides.items()}
            work = out / p["slug"]
            work.mkdir(parents=True, exist_ok=True)
            for key in sorted(set(svgs["old"]) | set(svgs["new"])):
                n, old_png, new_png, diff_png = make_diff(svgs["old"].get(key), svgs["new"].get(key),
                                                          work, key)
                if not n:
                    for f in (old_png, new_png):
                        if f:
                            f.unlink()
                else:
                    report.append((p, key, n, [x.relative_to(out).as_posix() if x else None
                                               for x in (old_png, new_png, diff_png)]))
                for g in work.glob("*.gray.png"):
                    g.unlink()

        write_diff_index(out, report, base, touched)
        lines = ["## Visual diff", "",
                 f"Compared against `{base[:10]}`. Download the **visual-diff** artifact and open "
                 "`index.html` (red = removed, green = added).", ""]
        if not touched:
            lines.append("No schematic or PCB files changed.")
        elif not report:
            lines.append("Schematic/PCB files changed, but nothing visible changed.")
        else:
            lines += ["| Project | Page / layer | Changed pixels |", "|---|---|---|"]
            lines += [f"| {p['name']} | `{key}` | {n:,} |" for p, key, n, _ in report]
        append_summary("\n".join(lines) + "\n")
        print("\n".join(lines))
        set_output("changed", "true" if report else "false")
    finally:
        git("worktree", "remove", "--force", str(base_tree))
        shutil.rmtree(tmp, ignore_errors=True)


def write_diff_index(out, report, base, touched):
    rows = []
    for p, key, n, (old, new, diff) in report:
        def img(src, label):
            if not src:
                return f"<figure><div class='none'>(not present)</div><figcaption>{label}</figcaption></figure>"
            return (f"<figure><a href='{html.escape(src)}'><img loading='lazy' src='{html.escape(src)}'></a>"
                    f"<figcaption>{label}</figcaption></figure>")
        rows.append(f"<section><h2>{html.escape(p['name'])} &mdash; {html.escape(key)}"
                    f" <small>({n:,} px changed)</small></h2><div class='row'>"
                    + img(diff, "diff (red removed, green added)") + img(old, "base") + img(new, "PR")
                    + "</div></section>")
    body = "\n".join(rows) or "<p>No visible changes.</p>"
    (out / "index.html").write_text(f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>KiCad Visual Diff</title>
<style>
 body{{font:14px system-ui,sans-serif;margin:16px;background:#f6f6f6;color:#222}}
 section{{background:#fff;border:1px solid #ddd;border-radius:6px;padding:12px;margin:0 0 16px}}
 h2{{font-size:16px;margin:0 0 8px}} small{{color:#777;font-weight:normal}}
 .row{{display:grid;grid-template-columns:2fr 1fr 1fr;gap:8px}}
 figure{{margin:0}} img{{width:100%;border:1px solid #ccc;background:#fff}}
 figcaption{{color:#666;font-size:12px}} .none{{padding:40px;text-align:center;color:#999;border:1px dashed #ccc}}
 @media (max-width:800px){{.row{{grid-template-columns:1fr}}}}
</style></head><body>
<h1>KiCad visual diff</h1><p>Base <code>{html.escape(base)}</code>; projects touched: {html.escape(', '.join(touched) or 'none')}</p>
{body}
</body></html>
""", encoding="utf-8")


# --------------------------------------------------------------------------- main

def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("projects")
    s = sub.add_parser("setup")
    s.add_argument("--libs-dir", default=os.path.join(os.path.expanduser("~"), "kicad-ext-libs"))
    sub.add_parser("hygiene")
    c = sub.add_parser("check")
    c.add_argument("project", help="project directory, e.g. hdw/DSP_board/rev_a/Audio_Visualiser_DSP")
    c.add_argument("--out", default="ci-out/reports")
    o = sub.add_parser("outputs")
    o.add_argument("project")
    o.add_argument("--out", default="ci-out/outputs")
    o.add_argument("--label", help="name suffix for zips, e.g. a tag or short SHA")
    o.add_argument("--no-3d", action="store_true")
    d = sub.add_parser("diff")
    d.add_argument("--base", required=True, help="base commit to compare against")
    d.add_argument("--out", default="ci-out/visual-diff")
    args = ap.parse_args()
    handler = {"projects": cmd_projects, "setup": cmd_setup, "hygiene": cmd_hygiene,
               "check": cmd_check, "outputs": cmd_outputs, "diff": cmd_diff}[args.cmd]
    sys.exit(handler(args) or 0)


if __name__ == "__main__":
    main()
