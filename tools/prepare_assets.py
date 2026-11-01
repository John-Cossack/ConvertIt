from pathlib import Path
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parent.parent
assets = root / "package" / "Assets"
assets.mkdir(parents=True, exist_ok=True)
image = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((8, 8, 248, 248), radius=52, fill="#202b44")
draw.rounded_rectangle((62, 72, 194, 180), radius=14, outline="#d6e6ff", width=9)
draw.ellipse((86, 92, 110, 116), fill="#7daeff")
draw.polygon([(73, 166), (121, 119), (146, 143), (168, 123), (185, 166)], fill="#7daeff")
draw.line([(47, 57), (176, 57)], fill="#6fe0b1", width=12)
draw.polygon([(176, 39), (202, 57), (176, 75)], fill="#6fe0b1")
draw.line([(209, 202), (80, 202)], fill="#6fe0b1", width=12)
draw.polygon([(80, 184), (54, 202), (80, 220)], fill="#6fe0b1")
for filename, size in [("StoreLogo.png", 50), ("Logo150.png", 150), ("Logo44.png", 44)]:
    image.resize((size, size), Image.Resampling.LANCZOS).save(assets / filename)
image.save(root / "package" / "ConvertIt.ico", sizes=[(16,16), (32,32), (48,48), (64,64), (128,128), (256,256)])
