# One-time build helper: extract the Tcl and Tk script libraries out of the
# Tcl 9 zipfs (embedded in the DLLs) into real folders on disk, so PyInstaller
# can bundle them as _tcl_data / _tk_data. Needed because Python 3.14 + Tcl/Tk 9
# store these inside the DLL (path //zipfs:/...), and PyInstaller 6.21's tkinter
# hook does not populate them -> "Tcl data directory _tcl_data not found".
import tkinter, os, shutil, sys

here = os.path.dirname(os.path.abspath(__file__))
res = os.path.join(here, "build_res")
dst_tcl = os.path.join(res, "_tcl_data")
dst_tk = os.path.join(res, "_tk_data")
for d in (dst_tcl, dst_tk):
    if os.path.isdir(d):
        shutil.rmtree(d)
os.makedirs(res, exist_ok=True)

r = tkinter.Tk()
tcl_lib = r.tk.eval("info library")      # //zipfs:/lib/tcl/tcl_library
tk_lib = r.tk.eval("set tk_library")     # //zipfs:/lib/tk/tk_library

# Tcl's own [file copy] can read from the zipfs and write to a real path.
# Destination does not exist -> source is copied AS that path (contents at top).
r.tk.eval('file copy -force {%s} {%s}' % (tcl_lib, dst_tcl.replace("\\", "/")))
r.tk.eval('file copy -force {%s} {%s}' % (tk_lib, dst_tk.replace("\\", "/")))
r.destroy()

# Verify the key files landed.
print("TCL dst:", dst_tcl, "init.tcl:", os.path.isfile(os.path.join(dst_tcl, "init.tcl")))
print("TK  dst:", dst_tk, "tk.tcl:", os.path.isfile(os.path.join(dst_tk, "tk.tcl")))
print("tcl file count:", sum(len(f) for _, _, f in os.walk(dst_tcl)))
print("tk  file count:", sum(len(f) for _, _, f in os.walk(dst_tk)))
