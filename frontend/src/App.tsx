import React, { useEffect, useState } from 'react';
import { Shield, ShieldAlert, CheckCircle2, Server, ArrowRight } from 'lucide-react';

interface HealthData {
  status: string;
  version: string;
  models_loaded: string[];
}

export default function App(): React.JSX.Element {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/health')
      .then((res) => {
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}: Failed to reach backend`);
        }
        return res.json();
      })
      .then((data: HealthData) => {
        setHealth(data);
        setLoading(false);
      })
      .catch((err: Error) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  return (
    <div className="min-h-screen bg-[#0B0F14] text-[#E5E7EB] flex flex-col justify-between p-6 sm:p-12">
      <header className="max-w-5xl mx-auto w-full flex items-center justify-between border-b border-[#1F2937] pb-6">
        <div className="flex items-center space-x-3">
          <div className="p-2 rounded-lg bg-cyan-500/10 border border-cyan-500/30 text-[#22D3EE]">
            <Shield className="w-7 h-7" />
          </div>
          <div>
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-white flex items-center gap-2">
              StegaGuard
              <span className="text-xs font-mono font-normal px-2 py-0.5 rounded bg-cyan-950 text-[#22D3EE] border border-cyan-800">
                Phase 0
              </span>
            </h1>
            <p className="text-xs text-[#9CA3AF]">
              AI-Based Image Steganalysis with Cryptographic Verification
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="hidden sm:flex items-center gap-2 text-xs font-mono px-3 py-1.5 rounded-md bg-[#111827] border border-[#1F2937]">
            <Server className="w-3.5 h-3.5 text-cyan-400" />
            <span>FastAPI Backend</span>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto w-full my-auto py-12">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 items-center">
          <div>
            <div className="inline-flex items-center gap-2 text-xs font-mono uppercase tracking-wider text-[#22D3EE] mb-4">
              <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse"></span>
              System Status & Verification
            </div>
            <h2 className="text-3xl sm:text-4xl font-extrabold text-white tracking-tight mb-4">
              Covert Communication & Steganalysis Suite
            </h2>
            <p className="text-[#9CA3AF] text-sm sm:text-base leading-relaxed mb-6">
              StegaGuard pairs an offensive covert channel (AES-256-GCM + Ed25519 authenticated
              LSB steganography) with a defensive AI steganalyzer (statistical attacks,
              StegNet-Lite CNN with KV high-pass filter, and explainability heatmaps).
            </p>

            <div className="flex flex-wrap gap-4 text-xs font-mono text-[#9CA3AF]">
              <div className="flex items-center gap-1.5 bg-[#111827] px-3 py-2 rounded border border-[#1F2937]">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                <span>Verify-Before-Decrypt</span>
              </div>
              <div className="flex items-center gap-1.5 bg-[#111827] px-3 py-2 rounded border border-[#1F2937]">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                <span>Stateless Engine</span>
              </div>
              <div className="flex items-center gap-1.5 bg-[#111827] px-3 py-2 rounded border border-[#1F2937]">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                <span>ChaCha20 Permutation</span>
              </div>
            </div>
          </div>

          <div className="bg-[#111827] rounded-xl border border-[#1F2937] p-6 shadow-2xl">
            <h3 className="text-sm font-semibold text-white uppercase tracking-wider mb-4 flex items-center justify-between">
              <span>Backend Connection</span>
              <span className="text-xs font-mono text-[#9CA3AF]">GET /api/health</span>
            </h3>

            {loading && (
              <div className="flex items-center justify-center p-8 text-[#9CA3AF] text-sm animate-pulse">
                Pinging StegaGuard backend...
              </div>
            )}

            {!loading && health && (
              <div className="space-y-4">
                <div className="p-4 rounded-lg bg-emerald-950/30 border border-emerald-800/40 flex items-start gap-3">
                  <CheckCircle2 className="w-5 h-5 text-emerald-400 mt-0.5 shrink-0" />
                  <div>
                    <div className="text-sm font-medium text-emerald-300">
                      Backend Service Online
                    </div>
                    <div className="text-xs text-emerald-400/80 mt-0.5 font-mono">
                      API Version: {health.version} | Status: {health.status}
                    </div>
                  </div>
                </div>

                <div className="space-y-2 text-xs font-mono">
                  <div className="flex justify-between py-2 border-b border-[#1F2937]">
                    <span className="text-[#9CA3AF]">Models Loaded:</span>
                    <span className="text-white">
                      {health.models_loaded.length > 0
                        ? health.models_loaded.join(', ')
                        : 'None (Phase 0 scaffold)'}
                    </span>
                  </div>
                  <div className="flex justify-between py-2 border-b border-[#1F2937]">
                    <span className="text-[#9CA3AF]">Core Protocols:</span>
                    <span className="text-white">Argon2id / AES-GCM / Ed25519</span>
                  </div>
                  <div className="flex justify-between py-2">
                    <span className="text-[#9CA3AF]">Next Phase:</span>
                    <span className="text-[#22D3EE] font-semibold flex items-center gap-1">
                      Phase 1 (Crypto Core) <ArrowRight className="w-3 h-3" />
                    </span>
                  </div>
                </div>
              </div>
            )}

            {!loading && error && (
              <div className="p-4 rounded-lg bg-rose-950/30 border border-rose-800/40 flex items-start gap-3">
                <ShieldAlert className="w-5 h-5 text-rose-400 mt-0.5 shrink-0" />
                <div>
                  <div className="text-sm font-medium text-rose-300">
                    Backend Connection Standby
                  </div>
                  <div className="text-xs text-rose-400/80 mt-1">
                    {error}
                  </div>
                  <div className="text-xs text-[#9CA3AF] mt-2">
                    Start backend with: <code className="text-cyan-400">make run-backend</code>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </main>

      <footer className="max-w-5xl mx-auto w-full border-t border-[#1F2937] pt-6 flex flex-col sm:flex-row justify-between items-center text-xs text-[#9CA3AF] gap-4">
        <div>StegaGuard ISC Academic Research Project</div>
        <div className="font-mono text-cyan-400/70">Source of Truth: PROJECT_BLUEPRINT.md</div>
      </footer>
    </div>
  );
}
