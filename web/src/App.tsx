import { useEffect, useState } from "react";
import LoadingBar from "react-top-loading-bar";
import { loadingBar, track } from "./progress";

export default function App() {
  const [version, setVersion] = useState("…");

  useEffect(() => {
    track(fetch("/api/v1/health").then((r) => r.json()))
      .then((d) => setVersion(d.versi_model))
      .catch(() => setVersion("API tidak terhubung"));
  }, []);

  return (
    <>
      <LoadingBar ref={loadingBar} color="#2A78D6" shadow={false} />
      <main className="grid min-h-screen place-items-center bg-slate-50 text-slate-900">
        <div className="text-center">
          <h1 className="text-3xl font-semibold">TAPAL</h1>
          <p className="mt-2 text-sm text-slate-500">Versi {version}</p>
        </div>
      </main>
    </>
  );
}
