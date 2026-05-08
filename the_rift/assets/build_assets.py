"""
Run once to generate all static assets:
  - crown.png / crown_glow.png  (from heavy is the crown.stl)
  - noise_tile.png
"""
import struct, math, random, os
from PIL import Image, ImageDraw, ImageFilter

ASSET_DIR = os.path.dirname(__file__)
STL_PATH  = r"C:\Users\blhei\Downloads\heavy is the crown.stl"

# ---------------------------------------------------------------------------
# 1. Crown from STL
# ---------------------------------------------------------------------------
def _parse_stl(path):
    with open(path, "rb") as f:
        f.seek(84)
        verts = []
        num_tris = struct.unpack_from("<I", open(path, "rb").read(84)[80:])[0]
        for _ in range(num_tris):
            f.read(12)
            for _ in range(3):
                x, y, z = struct.unpack("<fff", f.read(12))
                verts.append((x, z))
            f.read(2)
    return verts

def _outline_polygon(verts):
    """
    Build an ordered outline polygon from the cloud of XZ points.
    Strategy: convex hull gives the outer silhouette cleanly for a simple crown shape.
    We then punch the interior prongs back in using the known geometry.
    For this crown the convex hull IS the right silhouette.
    """
    # Graham scan convex hull
    def cross(O, A, B):
        return (A[0]-O[0])*(B[1]-O[1]) - (A[1]-O[1])*(B[0]-O[0])

    pts = sorted(set([(round(x,3), round(z,3)) for x,z in verts]))
    if len(pts) < 3:
        return pts
    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]

def build_crown(size=320, padding=24):
    verts = _parse_stl(STL_PATH)
    hull  = _outline_polygon(verts)

    xs = [p[0] for p in hull]
    zs = [p[1] for p in hull]
    min_x, max_x = min(xs), max(xs)
    min_z, max_z = min(zs), max(zs)

    w_model = max_x - min_x
    h_model = max_z - min_z
    aspect  = w_model / h_model

    img_w = size
    img_h = int(size / aspect) + padding * 2

    def to_px(x, z):
        px = (x - min_x) / w_model * (img_w - padding*2) + padding
        # flip Z so top of model = top of image
        pz = (1 - (z - min_z) / h_model) * (img_h - padding*2) + padding
        return (px, pz)

    poly = [to_px(x, z) for x, z in hull]

    # --- base image (RGBA) ---
    img = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Gold fill with vertical gradient using line-by-line rasterisation
    mask = Image.new("L", (img_w, img_h), 0)
    ImageDraw.Draw(mask).polygon(poly, fill=255)

    gradient = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
    g_draw   = ImageDraw.Draw(gradient)
    # top bright -> bottom dark
    top_col    = (255, 230, 140, 255)   # bright gold tip
    mid_col    = (200, 168, 106, 255)   # brand gold
    bot_col    = (92,  69,  32,  255)   # dark base

    for row in range(img_h):
        t = row / img_h
        if t < 0.5:
            r2 = t * 2
            r = int(top_col[0] + (mid_col[0]-top_col[0])*r2)
            g = int(top_col[1] + (mid_col[1]-top_col[1])*r2)
            b = int(top_col[2] + (mid_col[2]-top_col[2])*r2)
        else:
            r2 = (t - 0.5) * 2
            r = int(mid_col[0] + (bot_col[0]-mid_col[0])*r2)
            g = int(mid_col[1] + (bot_col[1]-mid_col[1])*r2)
            b = int(mid_col[2] + (bot_col[2]-mid_col[2])*r2)
        g_draw.line([(0, row), (img_w, row)], fill=(r, g, b, 255))

    gradient.putalpha(mask)
    img.paste(gradient, mask=mask)

    # Sharp edge outline in dark gold
    draw = ImageDraw.Draw(img)
    draw.polygon(poly, outline=(92, 69, 32, 200))

    crown_path = os.path.join(ASSET_DIR, "crown.png")
    img.save(crown_path)
    print(f"Saved {crown_path}  ({img_w}x{img_h})")

    # --- glow version: blur heavily, tint gold ---
    glow = img.filter(ImageFilter.GaussianBlur(radius=18))
    # boost alpha and shift toward brighter gold
    r2, g2, b2, a2 = glow.split()
    import PIL.ImageEnhance as IE
    glow = Image.merge("RGBA", (r2, g2, b2, a2))
    glow_path = os.path.join(ASSET_DIR, "crown_glow.png")
    glow.save(glow_path)
    print(f"Saved {glow_path}")

# ---------------------------------------------------------------------------
# 2. Background noise tile
# ---------------------------------------------------------------------------
def build_noise(size=256):
    img  = Image.new("RGBA", (size, size), (0,0,0,0))
    data = img.load()
    random.seed(42)
    for y in range(size):
        for x in range(size):
            # very subtle grain — mostly transparent
            v = random.randint(0, 255)
            a = random.randint(0, 10)   # max 10/255 opacity
            data[x, y] = (v, v, v, a)
    path = os.path.join(ASSET_DIR, "noise_tile.png")
    img.save(path)
    print(f"Saved {path}")

# ---------------------------------------------------------------------------
if __name__ == "__main__":
    build_crown(size=320, padding=28)
    build_noise(size=256)
    print("All assets built.")
