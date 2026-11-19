"""Empaqueta entregables sin bases, secretos, cachés ni dependencias instaladas."""
from pathlib import Path
import shutil
import zipfile
import os

root=Path(__file__).resolve().parents[1]
out=Path(os.getenv('DELIVERY_DIR', str(root.parent/'entrega')))
out.mkdir(parents=True,exist_ok=True)
pdf=out/'Arquitectura_FrioAlerta.pdf'
shutil.copy2(root/'docs/Arquitectura_FrioAlerta.pdf',pdf)
archive=out/'FrioAlerta_Proyecto_Completo.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for file in sorted(root.rglob('*')):
        relative=file.relative_to(root)
        if not file.is_file() or any(part in {'__pycache__','data','.venv','.git'} for part in relative.parts) or file.name=='.env' or file.suffix=='.pyc':
            continue
        z.write(file,'frioalerta/'+relative.as_posix())
with zipfile.ZipFile(archive,'r') as verify:
    assert verify.testzip() is None
print(pdf)
print(archive)
