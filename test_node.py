"""Offline checks for the node modules — the half of the pack that needs ComfyUI imported.

`test_plan.py` covers `minimax_plan`, which imports nothing outside the standard library
and can therefore run anywhere. The guards that keep a bad wire out of the sampler live in
`minimax_director.py`, and API-key resolution lives in `minimax_media.py`; both reach into
ComfyUI, so they need this harness instead:

    python test_node.py

Nothing here samples, decodes or talks to a network. Run it with the same interpreter
ComfyUI uses — a portable install keeps one next to the ComfyUI folder:

    ..\\..\\..\\python_embeded\\python.exe test_node.py

Two things make the import work at all, and both are easy to trip over:

* the folder name has a hyphen, so the package is loaded under a synthetic module name;
* `minimax_media` registers aiohttp routes at import time and dies without a server, so
  `PromptServer.instance` has to exist before the import, not after.
"""
import importlib.util
import inspect
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
COMFY_ROOT = os.path.dirname(os.path.dirname(HERE))      # custom_nodes/<pack> -> ComfyUI

for path in (COMFY_ROOT, os.path.dirname(HERE)):
    if path not in sys.path:
        sys.path.insert(0, path)


def _stub_prompt_server():
    """A PromptServer with just enough surface for route registration at import time."""
    import server

    if getattr(server.PromptServer, "instance", None) is not None:
        return

    class _Routes:
        def post(self, *_a, **_k):
            return lambda fn: fn

        def get(self, *_a, **_k):
            return lambda fn: fn

    server.PromptServer.instance = types.SimpleNamespace(routes=_Routes())


def _load_package():
    _stub_prompt_server()
    name = "minimaxh3_director_undertest"
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(HERE, "__init__.py"),
        submodule_search_locations=[HERE])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return sys.modules[name + ".minimax_director"], sys.modules[name + ".minimax_media"]


director, media = _load_package()
package = sys.modules["minimaxh3_director_undertest"]

_results = []


def check(name, got, want):
    _results.append((got == want, name, got, want))


def check_raises(name, fn, needle):
    try:
        fn()
    except Exception as e:                                     # noqa: BLE001 - that is the check
        ok = needle in str(e)
        _results.append((ok, name, "raised %r" % str(e)[:90] if not ok else "raised", "raised"))
        return
    _results.append((False, name, "did not raise", "raised"))


# -------------------------------------------------- schema vs execute() signature
# ComfyUI passes every input by keyword, so an input declared in the schema with no
# matching parameter is a TypeError at run time and nowhere earlier — the whole graph
# dies on the node, after the models have loaded. Cheap to catch here instead.
def _schema_inputs(node_cls):
    schema = node_cls.define_schema()
    return [i.id for i in schema.inputs]


for node_cls in (package.MiniMaxH3Director, package.MiniMaxH3EnhancePrompt,
                 package.MiniMaxH3PreviewOverride, package.MiniMaxH3RetakeStitch,
                 package.MiniMaxH3SaveLastFrame):
    params = inspect.signature(node_cls.execute.__func__).parameters
    accepts_kwargs = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())
    missing = [] if accepts_kwargs else [
        name for name in _schema_inputs(node_cls) if name not in params]
    check("%s: every schema input has an execute() parameter" % node_cls.__name__,
          missing, [])

# and the reverse for the two inputs added in 0.2.1, so a rename cannot quietly orphan one
check("width and height are declared on the Director",
      [n for n in ("width", "height") if n in _schema_inputs(package.MiniMaxH3Director)],
      ["width", "height"])
# trap 9: widgets are serialised positionally, so a new one has to be last or every value
# after it lands on the wrong input in workflows already saved
check("api_key_env is the Enhance node's last widget",
      _schema_inputs(package.MiniMaxH3EnhancePrompt)[-1], "api_key_env")


# ------------------------------------------------------------------ resolve_size (#14)
# The settings panel owns custom_width/custom_height and hides them, so these two sockets
# are the only route a resolution node has into the canvas.
rs = director.resolve_size

check("nothing connected leaves the panel's box alone", rs(1344, 768), (1344, 768))
check("an unconnected pair keeps 0 meaning 'derive from the image'", rs(0, 0), (0, 0))
check("a connected width overrides the panel", rs(1344, 768, 1920, None), (1920, 768))
check("a connected height overrides the panel", rs(1344, 768, None, 1088), (1344, 1088))
check("both override", rs(0, 0, 864, 480), (864, 480))
check("floats off a resolution node are taken as pixels", rs(0, 0, 864.0, 480.0), (864, 480))

# A widget carries a minimum; a wire carries none. 0 is what an upstream node hands over
# when its own value was never set, which is the same trap `duration` fell into in #4.
check_raises("a connected width of 0 is refused by name",
             lambda: rs(1344, 768, 0, 768), "the connected 'width' is 0")
check_raises("a connected height of 0 is refused by name",
             lambda: rs(1344, 768, 1344, 0), "the connected 'height' is 0")
check_raises("a negative width is refused too",
             lambda: rs(0, 0, -8, None), "the connected 'width' is -8")
check_raises("the message says how to ask for the automatic canvas",
             lambda: rs(0, 0, 0, None), "Leave the socket unconnected")

# ---------------------------------------------------------------- resolve_window (#4)
# Same automation hazard, older sockets — checked here because the harness now exists.
rw = director.resolve_window
check("no automation returns the panel's window", rw({}, 24.0, 0, 120), (0, 120))
check("a connected duration is converted to frames and replaces the panel's",
      rw({}, 24.0, 0, 120, None, None, 7.0), (0, 168))
check("a connected start is converted too", rw({}, 24.0, 0, 120, 2.0), (48, 120))
check_raises("a connected duration of 0 is refused",
             lambda: rw({}, 24.0, 0, 120, None, None, 0.0), "the connected 'duration' is 0")
check_raises("a negative start is refused",
             lambda: rw({}, 24.0, 0, 120, -1.0), "cannot be negative")

# ------------------------------------------------------------------- API keys (#15)
key = media.resolve_api_key
os.environ.pop("MINIMAX_DIRECTOR_VLM_API_KEY", None)
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("MMXD_TEST_KEY", None)

check("no key anywhere is an empty string, not None", key({}), "")
check("no key means no Authorization header at all", media._auth_headers(""), None)
check("None is a missing key too", media._auth_headers(None), None)
check("a key becomes a bearer header", media._auth_headers("sk-abc"),
      {"Authorization": "Bearer sk-abc"})
check("whitespace around a key is not sent", media._auth_headers("  sk-abc  "),
      {"Authorization": "Bearer sk-abc"})

check("an explicit key wins", key({"api_key": "sk-explicit"}), "sk-explicit")
check("a blank explicit key falls through rather than sending an empty bearer",
      key({"api_key": "   "}), "")

os.environ["MMXD_TEST_KEY"] = "sk-from-named-var"
check("a named environment variable is read", key({"api_key_env": "MMXD_TEST_KEY"}),
      "sk-from-named-var")
check("the explicit key still wins over the named variable",
      key({"api_key": "sk-explicit", "api_key_env": "MMXD_TEST_KEY"}), "sk-explicit")
check("a variable that does not exist is not an error",
      key({"api_key_env": "MMXD_NO_SUCH_VAR"}), "")

os.environ["OPENAI_API_KEY"] = "sk-openai"
check("OPENAI_API_KEY is the last resort", key({}), "sk-openai")
os.environ["MINIMAX_DIRECTOR_VLM_API_KEY"] = "sk-pack"
check("the pack's own variable is preferred over OPENAI_API_KEY", key({}), "sk-pack")
check("a named variable still beats both",
      key({"api_key_env": "MMXD_TEST_KEY"}), "sk-from-named-var")
for var in ("MMXD_TEST_KEY", "OPENAI_API_KEY", "MINIMAX_DIRECTOR_VLM_API_KEY"):
    os.environ.pop(var, None)

# The Enhance node's widget names a variable rather than holding a key, because widget
# values are serialised into the workflow. Guard the shape it passes in.
check("an empty widget resolves to no key", key({"api_key_env": ""}), "")

# -------------------------------------------------------- Save Last Frame node
# It sits mid-chain after VAEDecode, so the two things that must hold are that the batch
# comes out untouched and that exactly one file is written — the last frame, whatever the
# length. Saving goes to a temp directory here; the real output folder is left alone.
import shutil
import tempfile

import folder_paths
import torch

last_frame = package.MiniMaxH3SaveLastFrame
_real_output = folder_paths.get_output_directory()
_tmp_output = tempfile.mkdtemp(prefix="mmxd_lastframe_test_")
folder_paths.set_output_directory(_tmp_output)
try:
    def batch(n):
        """[n, 4, 4, 3], each frame a distinct grey so the saved one is identifiable.

        Scaled to stay well inside 0..1: the saver truncates 255*value to uint8, and two
        frames that both clip to 255 would make this test unable to fail.
        """
        frames = [torch.full((1, 4, 4, 3), (i + 1) / 512.0) for i in range(n)]
        return torch.cat(frames, dim=0)

    def written():
        return sorted(f for _r, _d, fs in os.walk(_tmp_output) for f in fs)

    images = batch(124)

    off = last_frame.execute(images, save=False, filename_prefix="off")
    check("save off returns the batch itself, not a copy", off.args[0] is images, True)
    check("save off writes nothing", written(), [])

    on = last_frame.execute(images, save=True, filename_prefix="on")
    check("save on still passes the whole batch through", on.args[0] is images, True)
    check("save on writes exactly one file", len(written()), 1)
    check("the file is a png", written()[0].endswith(".png"), True)
    check("the ui reports the one saved frame", len(on.ui.results), 1)

    # the frame saved has to be the LAST one, not the first — read it back and compare
    from PIL import Image as _PILImage
    saved_path = os.path.join(_tmp_output, on.ui.results[0]["subfolder"],
                              on.ui.results[0]["filename"])
    px = _PILImage.open(saved_path).convert("RGB").getpixel((0, 0))[0]
    expect_last = int(255.0 * float(images[-1, 0, 0, 0].item()))
    expect_first = int(255.0 * float(images[0, 0, 0, 0].item()))
    check("the saved pixel is the last frame's", px, expect_last)
    check("...and the two frames are distinguishable, so that check can fail",
          expect_last != expect_first, True)

    # a one-frame batch has a last frame like any other
    solo = last_frame.execute(batch(1), save=True, filename_prefix="solo")
    check("a single-frame batch saves that frame", len(solo.ui.results), 1)

    # and an empty one must not take a finished render down with it
    empty = torch.zeros((0, 4, 4, 3))
    before = len(written())
    out = last_frame.execute(empty, save=True, filename_prefix="empty")
    check("an empty batch passes through instead of raising", out.args[0] is empty, True)
    check("an empty batch writes nothing", len(written()), before)
    check("an empty batch reports no ui", getattr(out, "ui", None), None)
finally:
    folder_paths.set_output_directory(_real_output)
    shutil.rmtree(_tmp_output, ignore_errors=True)

check("the real output directory is restored", folder_paths.get_output_directory(),
      _real_output)


# ------------------------------------------------------------------- report
failed = [r for r in _results if not r[0]]
for ok, name, got, want in _results:
    if not ok:
        print("FAIL  %s\n        got:  %r\n        want: %r" % (name, got, want))
print("\n%d checks, %d passed, %d failed"
      % (len(_results), len(_results) - len(failed), len(failed)))
sys.exit(1 if failed else 0)
