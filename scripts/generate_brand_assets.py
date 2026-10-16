"""
ScanBooks Brand Asset Generator & Optimizer
Generates high-resolution, compressed transparent PWA icons, favicons, and web logos
from the user's transparent master logo PNG.
"""

import os

from PIL import Image

MASTER_IMAGE = r"C:\Users\Admin\.gemini\antigravity\brain\c97756d9-b560-4de5-b579-e772b0e4289d\.user_uploaded\media_1792154145501_dee76527.png"
STATIC_DIR = r"D:\projects\aibilling\static"
ICONS_DIR = os.path.join(STATIC_DIR, "icons")
IMG_DIR = os.path.join(STATIC_DIR, "img")

os.makedirs(ICONS_DIR, exist_ok=True)
os.makedirs(IMG_DIR, exist_ok=True)


def main():
    print(f"Loading master transparent logo from {MASTER_IMAGE}...")
    master = Image.open(MASTER_IMAGE).convert("RGBA")

    # Exact bounding boxes from 1024x1024 transparent PNG:
    # Symbol: (165, 253, 782, 627)
    # Text: (195, 681, 828, 770)
    # Full: (165, 253, 828, 770)
    crop_sym = master.crop((165, 253, 782, 627))
    crop_txt = master.crop((195, 681, 828, 770))
    crop_full = master.crop((165, 253, 828, 770))

    # --- 1. TIGHT SYMBOL (TRANSPARENT PNG FOR NAVBARS / SIDEBARS / HEADERS) ---
    p_trans = os.path.join(IMG_DIR, "logo-icon.png")
    p_trans_webp = os.path.join(IMG_DIR, "logo-icon.webp")
    crop_sym.save(p_trans, format="PNG", optimize=True)
    crop_sym.save(p_trans_webp, format="WEBP", quality=95, method=6)
    print(f"Saved logo-icon.png ({os.path.getsize(p_trans)} B)")
    print(f"Saved logo-icon.webp ({os.path.getsize(p_trans_webp)} B)")

    # --- 2. FULL VERTICAL LOGO (TRANSPARENT PNG) ---
    full_logo_path_png = os.path.join(IMG_DIR, "logo.png")
    full_logo_path_webp = os.path.join(IMG_DIR, "logo.webp")
    crop_full.save(full_logo_path_png, format="PNG", optimize=True)
    crop_full.save(full_logo_path_webp, format="WEBP", quality=95, method=6)
    print(f"Saved logo.png ({os.path.getsize(full_logo_path_png)} B)")
    print(f"Saved logo.webp ({os.path.getsize(full_logo_path_webp)} B)")

    # --- 3. HORIZONTAL BANNER LOGO (TRANSPARENT PNG) ---
    target_h = 140
    sym_w = int(crop_sym.width * (target_h / crop_sym.height))
    sym_res = crop_sym.resize((sym_w, target_h), Image.Resampling.LANCZOS)
    txt_h = 75
    txt_w = int(crop_txt.width * (txt_h / crop_txt.height))
    txt_res = crop_txt.resize((txt_w, txt_h), Image.Resampling.LANCZOS)
    gap = 24
    total_w = sym_w + gap + txt_w
    total_h = target_h

    horiz = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))
    horiz.paste(sym_res, (0, 0), sym_res)
    horiz.paste(txt_res, (sym_w + gap, (target_h - txt_h) // 2), txt_res)

    horiz_path_png = os.path.join(IMG_DIR, "logo-horizontal.png")
    horiz_path_webp = os.path.join(IMG_DIR, "logo-horizontal.webp")
    horiz.save(horiz_path_png, format="PNG", optimize=True)
    horiz.save(horiz_path_webp, format="WEBP", quality=95, method=6)
    print(f"Saved logo-horizontal.png ({os.path.getsize(horiz_path_png)} B)")
    print(f"Saved logo-horizontal.webp ({os.path.getsize(horiz_path_webp)} B)")

    # --- 4. SQUARE ICONS (TRANSPARENT BACKGROUND) ---
    def make_square_icon(size, pad_ratio=0.08):
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        max_dim = int(size * (1.0 - (pad_ratio * 2)))
        scale = min(max_dim / crop_sym.width, max_dim / crop_sym.height)
        new_w = max(1, int(crop_sym.width * scale))
        new_h = max(1, int(crop_sym.height * scale))
        scaled = crop_sym.resize((new_w, new_h), Image.Resampling.LANCZOS)
        offset = ((size - new_w) // 2, (size - new_h) // 2)
        canvas.paste(scaled, offset, scaled)
        return canvas

    icon_512 = make_square_icon(512, pad_ratio=0.05)
    p512 = os.path.join(ICONS_DIR, "icon-512.png")
    icon_512.save(p512, format="PNG", optimize=True)
    print(f"Saved icon-512.png ({os.path.getsize(p512)} B)")

    icon_192 = make_square_icon(192, pad_ratio=0.05)
    p192 = os.path.join(ICONS_DIR, "icon-192.png")
    icon_192.save(p192, format="PNG", optimize=True)
    print(f"Saved icon-192.png ({os.path.getsize(p192)} B)")

    # Apple Touch Icon: iOS looks best with clean white or transparent
    # iOS home screen renders black if alpha is empty, so apple-touch-icon uses clean white canvas
    apple_canvas = Image.new("RGBA", (180, 180), (255, 255, 255, 255))
    apple_sym = make_square_icon(180, pad_ratio=0.08)
    apple_canvas.alpha_composite(apple_sym)
    apple_canvas = apple_canvas.convert("RGB")
    p_apple = os.path.join(ICONS_DIR, "apple-touch-icon.png")
    apple_canvas.save(p_apple, format="PNG", optimize=True)
    print(f"Saved apple-touch-icon.png ({os.path.getsize(p_apple)} B)")

    # --- 5. FAVICONS (32x32, 16x16, and multi-size .ico) ---
    fav32 = make_square_icon(32, pad_ratio=0.02)
    p_fav32 = os.path.join(ICONS_DIR, "favicon-32x32.png")
    fav32.save(p_fav32, format="PNG", optimize=True)

    fav16 = make_square_icon(16, pad_ratio=0.0)
    p_fav16 = os.path.join(ICONS_DIR, "favicon-16x16.png")
    fav16.save(p_fav16, format="PNG", optimize=True)

    p_ico = os.path.join(ICONS_DIR, "favicon.ico")
    p_ico_root = os.path.join(STATIC_DIR, "favicon.ico")
    icon_512.save(p_ico, format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])
    icon_512.save(p_ico_root, format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])
    print(f"Saved favicon.ico ({os.path.getsize(p_ico)} B)")

    print("\n--- Brand Asset Generation Complete! ---")


if __name__ == "__main__":
    main()
