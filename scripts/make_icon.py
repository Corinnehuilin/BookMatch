"""Draw the original BookMatch app icon locally."""

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "assets" / "bookmatch-icon.png"
WINDOWS_OUTPUT = ROOT / "assets" / "bookmatch-icon.ico"


def main() -> None:
    size = 1024
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((24, 24, 1000, 1000), radius=228, fill="#254b3b")
    draw.rounded_rectangle((72, 72, 952, 952), radius=196, outline="#416b53", width=8)
    # Warm paper pages and a slim, golden reading marker.
    draw.polygon([(177, 302), (450, 337), (512, 390), (512, 766), (440, 720), (177, 690)], fill="#f6f1df")
    draw.polygon([(847, 302), (574, 337), (512, 390), (512, 766), (584, 720), (847, 690)], fill="#fff9e9")
    draw.line([(512, 390), (512, 766)], fill="#c5d2b9", width=15)
    draw.arc((194, 322, 482, 710), 258, 348, fill="#c1cdb8", width=13)
    draw.arc((542, 322, 830, 710), 192, 282, fill="#d2d8c3", width=13)
    draw.polygon([(512, 160), (553, 238), (631, 279), (553, 320), (512, 398),
                  (471, 320), (393, 279), (471, 238)], fill="#e9bf7b")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(OUTPUT)
    canvas.save(WINDOWS_OUTPUT, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(OUTPUT)
    print(WINDOWS_OUTPUT)


if __name__ == "__main__":
    main()
