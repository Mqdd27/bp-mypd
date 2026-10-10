import type { ReactNode } from "react";

// The five evidence levels required by the documentation contract.
const LEVELS = {
  general: { label: "Proses Umum RS Indonesia", cls: "conf-general" },
  verified: { label: "Terverifikasi di Kode", cls: "conf-verified" },
  inferred: { label: "Inferensi dari Kode", cls: "conf-inferred" },
  confirm: { label: "Perlu Konfirmasi RS", cls: "conf-confirm" },
  notfound: { label: "Tidak Ditemukan di Repo", cls: "conf-notfound" },
} as const;

export type ConfidenceLevel = keyof typeof LEVELS;

export function Confidence({
  level,
  children,
}: {
  level: ConfidenceLevel;
  children?: ReactNode;
}) {
  const { label, cls } = LEVELS[level];
  return (
    <span className={`conf-badge ${cls}`}>
      {label}
      {children ? <span className="conf-note"> · {children}</span> : null}
    </span>
  );
}
