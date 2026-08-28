# -*- coding: utf-8 -*-
"""Execute the workbook in place via nbclient (jupyter CLI entry point absent)."""
from pathlib import Path
import nbformat
from nbclient import NotebookClient

HERE = Path(__file__).resolve().parent
NB = HERE / "step_method_workbook.ipynb"

nb = nbformat.read(NB, as_version=4)
client = NotebookClient(nb, timeout=600, kernel_name="python3",
                        resources={"metadata": {"path": str(HERE)}})
client.execute()
nbformat.write(nb, NB)
print("executed OK:", NB)
for i, c in enumerate(nb.cells):
    if c.cell_type == "code":
        errs = [o for o in c.get("outputs", []) if o.get("output_type") == "error"]
        if errs:
            print("CELL", i, "ERROR:", errs[0].get("ename"), errs[0].get("evalue"))
