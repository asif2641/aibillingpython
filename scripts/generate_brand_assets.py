"""
ScanBooks Brand Asset Generator & Optimizer
Generates high-resolution, compressed PWA icons, favicons, and web logos
from the master logo file.
"""

import os
from collections import deque

from PIL import Image, ImageFilter

MASTER_IMAGE = r"C:\Users\Admin\.gemini\antigravity\brain\c97756d9-b560-4de5-b579-e772b0e4289d\.user_uploaded\media_1792151804228_b59ee3f8.jpg"
STATIC_DIR = r"D:\projects\aibilling\static"
ICONS_DIR = os.path.join(STATIC_DIR, "icons")
IMG_DIR = os.path.join(STATIC_DIR, "img")

os.makedirs(ICONS_DIR, exist_ok=True)
os.makedirs(IMG_DIR, exist_ok=True)


def decontaminate_outer_background(img_rgb):
    """
    Floods outer near-white background into transparency,
    while preserving internal whites (such as the open book pages),
    and removes color fringe/haloing via alpha deconvolution.
    """
    w, h = img_rgb.size
    pixels = img_rgb.load()

    # BFS from all four outer image boundaries
    visited = set()
    q = deque()
    for x in range(w):
        q.append((x, 0))
        q.append((x, h - 1))
    for y in range(h):
        q.append((0, y))
        q.append((w - 1, y))

    outer_bg = set()
    while q:
        cx, cy = q.popleft()
        if (cx, cy) in visited:
            continue
        visited.add((cx, cy))
        r, g, b = pixels[cx, cy]
        if r >= 230 and g >= 230 and b >= 230:
            outer_bg.add((cx, cy))
            for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in visited:
                    q.append((nx, ny))

    # Mask generation
    mask = Image.new("L", (w, h), 255)
    m_pix = mask.load()
    for x, y in outer_bg:
        r, g, b = pixels[x, y]
        val = max(255 - r, 255 - g, 255 - b)
        if val <= 10:
            m_pix[x, y] = 0
        else:
            m_pix[x, y] = int(min(255, (val / 25.0) * 255))

    smooth_mask = mask.filter(ImageFilter.GaussianBlur(radius=0.5))
    sm_pix = smooth_mask.load()

    # Reconstruct RGBA with decontaminated colors
    result = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    r_pix = result.load()

    for y in range(h):
        for x in range(w):
            a = sm_pix[x, y]
            if a == 0:
                r_pix[x, y] = (0, 0, 0, 0)
            else:
                r, g, b = pixels[x, y]
                alpha_f = a / 255.0
                if alpha_f < 0.98:
                    true_r = max(0, min(255, int((r - (1.0 - alpha_f) * 255) / alpha_f)))
                    true_g = max(0, min(255, int((g - (1.0 - alpha_f) * 255) / alpha_f)))
                    true_b = max(0, min(255, int((b - (1.0 - alpha_f) * 255) / alpha_f)))
                else:
                    true_r, true_g, true_b = r, g, b
                r_pix[x, y] = (true_r, true_g, true_b, a)

    return result


def main():
    print(f"Loading master logo from {MASTER_IMAGE}...")
    master = Image.open(MASTER_IMAGE).convert("RGB")
    w, h = master.size

    # Exact bounding boxes measured from master 1024x1024:
    # Symbol: (164, 252, 782, 628)
    # Text: (194, 681, 831, 771)
    crop_sym = master.crop((164, 252, 782, 628))
    crop_txt = master.crop((194, 681, 831, 771))
    crop_full = master.crop((140, 220, 850, 790))

    # --- 1. FULL VERTICAL LOGO ---
    full_logo_path_png = os.path.join(IMG_DIR, "logo.png")
    full_logo_path_webp = os.path.join(IMG_DIR, "logo.webp")
    # Resize full logo to max 720 width for crisp retina display
    scale_full = 720.0 / crop_full.width if crop_full.width > 720 else 1.0
    full_resized = crop_full.resize(
        (int(crop_full.width * scale_full), int(crop_full.height * scale_full)),
        Image.Resampling.LANCZOS,
    )
    full_resized.save(full_logo_path_png, format="PNG", optimize=True)
    full_resized.save(full_logo_path_webp, format="WEBP", quality=90, method=6)
    print(f"Saved logo.png ({os.path.getsize(full_logo_path_png)} B)")
    print(f"Saved logo.webp ({os.path.getsize(full_logo_path_webp)} B)")

    # --- 2. HORIZONTAL BANNER LOGO ---
    target_h = 140
    sym_w = int(crop_sym.width * (target_h / crop_sym.height))
    sym_res = crop_sym.resize((sym_w, target_h), Image.Resampling.LANCZOS)
    txt_h = 75
    txt_w = int(crop_txt.width * (txt_h / crop_txt.height))
    txt_res = crop_txt.resize((txt_w, txt_h), Image.Resampling.LANCZOS)
    gap = 24
    pad_h = 14
    total_w = sym_w + gap + txt_w + 32
    total_h = target_h + (pad_h * 2)

    horiz = Image.new("RGB", (total_w, total_h), (255, 255, 255))
    horiz.paste(sym_res, (16, pad_h))
    horiz.paste(txt_res, (16 + sym_w + gap, pad_h + (target_h - txt_h) // 2))

    horiz_path_png = os.path.join(IMG_DIR, "logo-horizontal.png")
    horiz_path_webp = os.path.join(IMG_DIR, "logo-horizontal.webp")
    horiz.save(horiz_path_png, format="PNG", optimize=True)
    horiz.save(horiz_path_webp, format="WEBP", quality=90, method=6)
    print(f"Saved logo-horizontal.png ({os.path.getsize(horiz_path_png)} B)")
    print(f"Saved logo-horizontal.webp ({os.path.getsize(horiz_path_webp)} B)")

    # --- 3. SQUARE PWA & APP ICONS (Solid clean white background for PWA maskable compliance) ---
    def make_square_icon(size, pad_ratio=0.15):
        canvas = Image.new("RGB", (size, size), (255, 255, 255))
        max_dim = int(size * (1.0 - (pad_ratio * 2)))
        scale = min(max_dim / crop_sym.width, max_dim / crop_sym.height)
        new_w = max(1, int(crop_sym.width * scale))
        new_h = max(1, int(crop_sym.height * scale))
        scaled = crop_sym.resize((new_w, new_h), Image.Resampling.LANCZOS)
        offset = ((size - new_w) // 2, (size - new_h) // 2)
        canvas.paste(scaled, offset)
        return canvas

    icon_512 = make_square_icon(512, pad_ratio=0.12)
    p512 = os.path.join(ICONS_DIR, "icon-512.png")
    icon_512.save(p512, format="PNG", optimize=True)
    print(f"Saved icon-512.png ({os.path.getsize(p512)} B)")

    icon_192 = make_square_icon(192, pad_ratio=0.12)
    p192 = os.path.join(ICONS_DIR, "icon-192.png")
    icon_192.save(p192, format="PNG", optimize=True)
    print(f"Saved icon-192.png ({os.path.getsize(p192)} B)")

    apple_icon = make_square_icon(180, pad_ratio=0.12)
    p_apple = os.path.join(ICONS_DIR, "apple-touch-icon.png")
    apple_icon.save(p_apple, format="PNG", optimize=True)
    print(f"Saved apple-touch-icon.png ({os.path.getsize(p_apple)} B)")

    # --- 4. FAVICONS (32x32, 16x16, and multi-size .ico) ---
    fav32 = make_square_icon(32, pad_ratio=0.08)
    p_fav32 = os.path.join(ICONS_DIR, "favicon-32x32.png")
    fav32.save(p_fav32, format="PNG", optimize=True)

    fav16 = make_square_icon(16, pad_ratio=0.05)
    p_fav16 = os.path.join(ICONS_DIR, "favicon-16x16.png")
    fav16.save(p_fav16, format="PNG", optimize=True)

    p_ico = os.path.join(ICONS_DIR, "favicon.ico")
    p_ico_root = os.path.join(STATIC_DIR, "favicon.ico")
    icon_512.save(p_ico, format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])
    icon_512.save(p_ico_root, format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])
    print(f"Saved favicon.ico ({os.path.getsize(p_ico)} B)")

    # --- 5. CLEAN TRANSPARENT SYMBOL ICON ---
    print("Generating decontaminated transparent symbol icon...")
    clean_trans = decontaminate_outer_background(icon_512)
    p_trans = os.path.join(IMG_DIR, "logo-icon.png")
    p_trans_webp = os.path.join(IMG_DIR, "logo-icon.webp")
    clean_trans.save(p_trans, format="PNG", optimize=True)
    clean_trans.save(p_trans_webp, format="WEBP", quality=95, method=6)
    print(f"Saved logo-icon.png ({os.path.getsize(p_trans)} B)")
    print(f"Saved logo-icon.webp ({os.path.getsize(p_trans_webp)} B)")

    print("\n--- Brand Asset Generation Complete! ---")


if __name__ == "__main__":
    main()
