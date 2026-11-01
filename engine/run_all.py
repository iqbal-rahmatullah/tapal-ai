import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

from engine.data import LAB, is_dev, label, out_dir

HEADS = ["embedding", "embedding", "ngram"]
HKEVAL = LAB / "hkeval" / "jalankan.py"
CPU_SLOTS = 4
# (name, arguments after `python3 -m`, stages it waits for, resource); "gpu" stages run one at a time so embedding never meets the LLM.
STAGES = [
    ("ai1", ["engine.ai1_dev"], [], "cpu"),
    ("garis", ["engine.lines_dev"], ["ai1"], "cpu"),
    ("ai4", ["engine.ai4_dev"], [], "cpu"),
    ("ai2_kata_kunci", ["engine.ai2_dev", "kata_kunci"], [], "cpu"),
    ("ai2_fisiologi", ["engine.ai2_dev", "fisiologi"], [], "cpu"),
    ("ai2_cepat", ["engine.ai2_dev", "cepat"], [], "cpu"),
    ("ai2_beban", ["engine.ai2_dev", "beban_jejak"], [], "cpu"),
    ("ai2_embed", ["engine.ai2_dev", "embed_dunia"], [], "gpu"),
    ("ai2_baca", ["engine.ai2_dev", "baca"], ["ai2_embed"], "gpu"),
    ("ai2_asersi", ["engine.ai2_dev", "asersi", "ngram", "embedding"] if is_dev() else ["engine.ai2_dev", "asersi_dunia", *HEADS],
     ["ai2_embed"], "cpu"),
    ("ai2_rs_modus", ["engine.ai2_dev", "rs_modus", *HEADS], ["ai2_kata_kunci", "ai2_fisiologi", "ai2_cepat", "ai2_embed"], "cpu"),
    ("ai2_plasebo", ["engine.ai2_dev", "plasebo_modus", *HEADS], ["ai2_embed"], "cpu"),
    ("ai2_berlapis", ["engine.ai2_dev", "berlapis", *HEADS], ["ai2_baca", "ai2_kata_kunci", "ai2_fisiologi", "ai2_cepat"], "cpu"),
    ("ai3_skor_jujur", ["engine.ai3_worlds", "skor_jujur"], [], "cpu"),
    ("ai3_varian", ["engine.ai3_worlds"], ["ai2_baca"], "gpu"),
    ("ai3_simulasi", ["engine.ai3_dev"], ["ai1", "ai2_rs_modus"], "cpu"),
    ("ai3_simulasi_ai1_jujur", ["engine.ai3_dev", "ai1_jujur"], ["ai3_simulasi", "ai3_skor_jujur"], "cpu"),
    ("ai3_adaptasi", ["engine.ai3_dev", "adaptasi"], ["ai3_simulasi", "ai3_varian"], "cpu"),
    ("ai3_adaptasi_ai1_jujur", ["engine.ai3_dev", "adaptasi", "ai1_jujur"], ["ai3_simulasi", "ai3_varian", "ai3_skor_jujur"], "cpu"),
    ("ai3_urutan", ["engine.ai3_dev", "urutan"], ["ai3_simulasi", "ai3_varian"], "cpu"),
    ("ai3_beban", ["engine.ai3_dev", "beban"], ["ai3_simulasi", "ai3_varian"], "cpu"),
]


def memory_free() -> int:
    text = subprocess.run(["memory_pressure"], capture_output=True, text=True).stdout
    found = re.search(r"free percentage: (\d+)%", text)
    return int(found.group(1)) if found else 100


def stamp() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def main(only: set[str] | None = None) -> int:
    marks = out_dir("run-all")
    marks.mkdir(parents=True, exist_ok=True)
    stages = [s for s in STAGES if only is None or s[0] in only]
    names = {s[0] for s in stages}
    done = {n for n in names if (marks / f"{n}.json").exists() and json.loads((marks / f"{n}.json").read_text()).get("kode_keluar") == 0}
    if HKEVAL.exists() and (only is None or "hkeval" in only):
        stages.append(("hkeval", [str(HKEVAL), label().replace(" ", "-").lower()], ["ai1"], "cpu"))
        names.add("hkeval")
    failed, running = set(), {}
    env = {**os.environ, "OMP_NUM_THREADS": os.environ.get("OMP_NUM_THREADS", "2")}
    log = (marks / "kejadian.log").open("a")
    log.write(f"{stamp()} mulai {label()}, sudah selesai {sorted(done)}\n")
    while True:
        for name, (proc, started, kind, handle) in list(running.items()):
            if proc.poll() is None:
                continue
            handle.close()
            del running[name]
            record = {"tahap": name, "mulai": started, "selesai": stamp(), "kode_keluar": proc.returncode, "dunia": label()}
            if proc.returncode == 0:
                done.add(name)
                (marks / f"{name}.json").write_text(json.dumps(record, ensure_ascii=False, indent=1))
            else:
                failed.add(name)
            log.write(f"{stamp()} {name} selesai kode {proc.returncode}\n")
            log.flush()
        blocked = {s[0] for s in stages if any(d in failed or (d not in names and d not in done) for d in s[2])}
        ready = [s for s in stages if s[0] not in done | failed | blocked and s[0] not in running and all(d in done for d in s[2])]
        free = memory_free()
        # Under memory pressure the CPU stages give way first; the LLM keeps its slot (user rule 1 Nov 2026).
        cpu_slots = CPU_SLOTS if free >= 25 else (2 if free >= 15 else 1)
        for name, args, _, kind in ready:
            busy = [k for _, _, k, _ in running.values()]
            if (kind == "gpu" and "gpu" in busy) or (kind == "cpu" and busy.count("cpu") >= cpu_slots):
                continue
            handle = (marks / f"{name}.log").open("a")
            command = [sys.executable, *args] if args[0].endswith(".py") else [sys.executable, "-m", *args]
            running[name] = (subprocess.Popen(command, stdout=handle, stderr=subprocess.STDOUT, env=env), stamp(), kind, handle)
            log.write(f"{stamp()} {name} mulai (memori bebas {free}%, slot CPU {cpu_slots})\n")
            log.flush()
        if not running and not ready:
            break
        time.sleep(5)
    log.write(f"{stamp()} berhenti; selesai {len(done)}, gagal {sorted(failed)}, tertahan {sorted(names - done - failed)}\n")
    log.close()
    print(json.dumps({"selesai": sorted(done), "gagal": sorted(failed), "tertahan": sorted(names - done - failed)}, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(set(sys.argv[1:]) or None))
