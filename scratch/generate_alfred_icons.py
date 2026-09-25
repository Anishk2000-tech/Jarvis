import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

def create_bat_insignia(size=1024):
    # Create RGBA canvas
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2
    scale = size / 512.0

    # Colors
    GOLD = (229, 169, 59, 255)       # Gotham Gold #e5a93b
    CYAN = (0, 240, 255, 255)        # Bat Cyan #00f0ff
    DARK_BG = (4, 14, 28, 240)       # Obsidian Glass
    RING_COLOR = (0, 240, 255, 180)

    # 1. Outer Tech Calibration Ring
    r_outer = int(230 * scale)
    draw.ellipse([cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer],
                 outline=RING_COLOR, width=int(3 * scale))

    # Outer tick marks (36 ticks)
    for i in range(36):
        ang = math.radians(i * 10)
        is_major = (i % 3 == 0)
        t_len = int(14 * scale if is_major else 7 * scale)
        r0 = r_outer - t_len
        r1 = r_outer
        x0 = cx + r0 * math.cos(ang)
        y0 = cy + r0 * math.sin(ang)
        x1 = cx + r1 * math.cos(ang)
        y1 = cy + r1 * math.sin(ang)
        col = CYAN if is_major else (0, 240, 255, 90)
        draw.line([x0, y0, x1, y1], fill=col, width=int(2 * scale if is_major else 1 * scale))

    # 2. Mid Octagonal / Hexagonal Target Ring
    r_mid = int(195 * scale)
    draw.ellipse([cx - r_mid, cy - r_mid, cx + r_mid, cy + r_mid],
                 outline=(229, 169, 59, 160), width=int(2 * scale))

    # Inner circular dark glass base
    r_inner = int(175 * scale)
    draw.ellipse([cx - r_inner, cy - r_inner, cx + r_inner, cy + r_inner],
                 fill=DARK_BG, outline=CYAN, width=int(2 * scale))

    # 3. Geometric Tactical Bat Insignia Polygon
    # Defining points for symmetrical tactical bat wings and cowl ears
    # Scaled around center (cx, cy)
    bat_pts_right = [
        (0, -68),        # Top center head notch
        (14, -88),       # Ear tip right
        (22, -58),       # Ear base right
        (65, -64),       # Top wing inner curve
        (130, -78),      # Top wing crest
        (165, -45),      # Wing tip outer
        (138, 5),        # Wing dip 1
        (110, -5),       # Wing tooth 1
        (85, 38),        # Wing dip 2
        (55, 28),        # Wing tooth 2
        (32, 68),        # Wing dip 3 / tail slope
        (0, 95),         # Bottom tail point
    ]

    # Mirror for full polygon
    poly_points = []
    # Left side (mirrored x)
    for x, y in reversed(bat_pts_right):
        if x != 0:
            poly_points.append((cx - x * scale * 0.95, cy + y * scale * 0.95))
    # Right side
    for x, y in bat_pts_right:
        poly_points.append((cx + x * scale * 0.95, cy + y * scale * 0.95))

    # Glow layer for the Bat Insignia
    glow_img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_img)
    glow_draw.polygon(poly_points, fill=(229, 169, 59, 180), outline=GOLD)
    glow_img = glow_img.filter(ImageFilter.GaussianBlur(radius=int(12 * scale)))
    img = Image.alpha_composite(img, glow_img)

    # Sharp foreground Bat Insignia
    draw = ImageDraw.Draw(img)
    draw.polygon(poly_points, fill=(240, 180, 50, 240), outline=CYAN, width=int(3 * scale))

    # Inner core eye slits
    eye_w = int(16 * scale)
    eye_h = int(6 * scale)
    eye_y = int(cy - 44 * scale)
    draw.polygon([(cx - 24 * scale, eye_y), (cx - 10 * scale, eye_y + eye_h), (cx - 14 * scale, eye_y - 2 * scale)], fill=CYAN)
    draw.polygon([(cx + 24 * scale, eye_y), (cx + 10 * scale, eye_y + eye_h), (cx + 14 * scale, eye_y - 2 * scale)], fill=CYAN)

    # 4. Wayne Enterprises / Batcave Telemetry Inscriptions
    # Corner crosshair markers
    c_off = int(220 * scale)
    for sx in (-1, 1):
        for sy in (-1, 1):
            px, py = cx + sx * c_off, cy + sy * c_off
            draw.line([px - 15 * scale, py, px + 15 * scale, py], fill=(0, 240, 255, 140), width=int(2 * scale))
            draw.line([px, py - 15 * scale, px, py + 15 * scale], fill=(0, 240, 255, 140), width=int(2 * scale))

    return img

if __name__ == "__main__":
    out_dir = Path("d:/Projects/Personal-Assistant/Mark-LIV/config")
    out_dir.mkdir(parents=True, exist_ok=True)

    master = create_bat_insignia(1024)

    # Save 512x512 PNGs
    img_512 = master.resize((512, 512), Image.Resampling.LANCZOS)
    img_512.save(out_dir / "alfred.png", format="PNG")
    img_512.save(out_dir / "alfred_bg.png", format="PNG")
    img_512.save(out_dir / "batman_logo.png", format="PNG")
    print("Saved alfred.png, alfred_bg.png, batman_logo.png")

    # Multi-resolution ICO
    ico_sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    master.save(out_dir / "alfred.ico", format="ICO", sizes=ico_sizes)
    print("Saved alfred.ico")

    # Also update jarvis.ico
    if (out_dir / "jarvis.ico").exists() and not (out_dir / "jarvis.ico.bak").exists():
        (out_dir / "jarvis.ico").rename(out_dir / "jarvis.ico.bak")
    master.save(out_dir / "jarvis.ico", format="ICO", sizes=ico_sizes)
    print("Updated jarvis.ico with backup")
