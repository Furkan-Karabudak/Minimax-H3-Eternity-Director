import numpy as np

# ---- H3 constants (verbatim from comfy/ldm/minimax/model.py) ----
FRAME_PER_TOKEN = (1, 4, 4, 4, 4)
FRAME_RESCALE   = 5.0 / 3.0

def video_spans(n, start=0):
    # span of local frame k (k indexes from `start` in global phase)
    return np.array([FRAME_RESCALE * FRAME_PER_TOKEN[(start + k) % 5] for k in range(n)])

def video_t_grid(n, origin, start_phase=0):
    # model's _video_t_grid: origin + EXCLUSIVE cumsum of spans (spans use start_phase)
    sp = video_spans(n, start_phase)
    excl = np.concatenate([[0.0], np.cumsum(sp)[:-1]])
    return origin + excl

def global_video_coord(i):
    # coordinate of global video-latent frame i under a fixed base (exclusive cumsum from 0)
    sp = video_spans(i, 0)
    return float(np.sum(sp))   # sum of spans[0..i-1]

# ---- scenario: two overlapping windows, DIFFERENT prompt lengths ----
# global video-latent frames 0..39; window A=[0,20), window B=[15,35); overlap = [15,20)
GA, NA = 0, 20
GB, NB = 15, 20
overlap = range(15, 20)
text_len_A = 100      # window A prompt -> 100 text tokens
text_len_B = 137      # window B prompt -> 137 text tokens (different!)
ref_off_A  = 0.0      # (no refs, keep simple)
ref_off_B  = 0.0

print("=== (1) PackedLayout AS-IS: origin = text_len + ref_offset, local span phase ===")
# each window is built independently, local frame index starts at 0 (phase 0)
cursA = text_len_A + ref_off_A
cursB = text_len_B + ref_off_B
gridA = video_t_grid(NA, cursA, start_phase=0)   # covers global 0..19
gridB = video_t_grid(NB, cursB, start_phase=0)   # covers global 15..34
print(" overlap frame | coord in A | coord in B | match?")
for gf in overlap:
    ca = gridA[gf - GA]
    cb = gridB[gf - GB]
    print("   %4d        | %9.3f | %9.3f | %s" % (gf, ca, cb, "YES" if abs(ca-cb)<1e-6 else "NO  (Δ=%.3f)"%(ca-cb)))

print("\n=== (2) FIX: global text-length-independent origin, block-aligned windows ===")
B = 512.0   # fixed base >= any window's text_len, so text never collides with video coords
# origin = B + global_video_coord(G); span phase = G % 5 (block-aligned so it equals global)
def window_grid_fixed(G, n):
    assert G % 5 == 0, "window must start on a 5-latent-frame block boundary"
    return video_t_grid(n, B + global_video_coord(G), start_phase=G % 5)
gridA2 = window_grid_fixed(GA, NA)
gridB2 = window_grid_fixed(GB, NB)
print(" overlap frame | coord in A | coord in B | match? | == global?")
for gf in overlap:
    ca = gridA2[gf - GA]; cb = gridB2[gf - GB]; cg = B + global_video_coord(gf)
    ok  = "YES" if abs(ca-cb)<1e-9 else "NO"
    okg = "YES" if abs(ca-cg)<1e-9 else "NO"
    print("   %4d        | %9.3f | %9.3f |  %s   |   %s" % (gf, ca, cb, ok, okg))

print("\n=== (3) why block-alignment matters: start a window at G=17 (17%%5=2) ===")
Gmis=17
# misaligned: if we (wrongly) use local phase 0 but claim origin for global 17
g_mis = video_t_grid(6, B + global_video_coord(Gmis), start_phase=0)
g_ref = np.array([B + global_video_coord(Gmis + j) for j in range(6)])
print(" frame off | local-phase-0 grid | true global | match?")
for j in range(6):
    print("    %2d     |     %9.3f     |  %9.3f  | %s" % (
        j, g_mis[j], g_ref[j], "YES" if abs(g_mis[j]-g_ref[j])<1e-9 else "NO"))
