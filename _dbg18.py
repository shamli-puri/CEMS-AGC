import io, inspect
from qrcode.image import svg
print(inspect.getsource(svg.SvgImage.save))
print(inspect.getsource(svg.SvgImage._write))
