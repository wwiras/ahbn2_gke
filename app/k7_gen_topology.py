"""Generate the unchanged physical topology, then attach K7 contract metadata."""
import argparse, sys
from pathlib import Path
import gen_topology
from k7_exp11_tools import enrich_topology

if __name__ == "__main__":
    p=argparse.ArgumentParser(); p.add_argument("--config",required=True); p.add_argument("--out",required=True); a=p.parse_args()
    sys.argv=["gen_topology.py","--config",a.config,"--out",a.out]; gen_topology.main()
    enrich_topology(Path(a.out),Path(a.config))
