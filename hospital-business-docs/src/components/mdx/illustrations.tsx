// Original conceptual illustrations. Colors come from Fumadocs theme tokens so
// they follow the light/dark toggle (not the OS preference).

function Box({
  x, y, w, h, title, sub, tone = "card",
}: {
  x: number; y: number; w: number; h: number; title: string; sub?: string;
  tone?: "card" | "accent" | "muted";
}) {
  const fill = { card: "var(--color-fd-card)", accent: "var(--color-fd-accent)", muted: "var(--color-fd-muted)" }[tone];
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={10} fill={fill}
        stroke="var(--color-fd-primary)" strokeWidth={1.5} />
      <text x={x + w / 2} y={y + (sub ? h / 2 - 4 : h / 2 + 5)} textAnchor="middle"
        fontSize={14} fontWeight={600} fill="var(--color-fd-foreground)">{title}</text>
      {sub ? (
        <text x={x + w / 2} y={y + h / 2 + 14} textAnchor="middle" fontSize={11}
          fill="var(--color-fd-muted-foreground)">{sub}</text>
      ) : null}
    </g>
  );
}

function Arrow({ d, label, lx, ly }: { d: string; label?: string; lx?: number; ly?: number }) {
  return (
    <g>
      <path d={d} fill="none" stroke="var(--color-fd-muted-foreground)" strokeWidth={1.5}
        markerEnd="url(#arrow)" />
      {label ? (
        <text x={lx} y={ly} textAnchor="middle" fontSize={11}
          fill="var(--color-fd-muted-foreground)">{label}</text>
      ) : null}
    </g>
  );
}

function Defs() {
  return (
    <defs>
      <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M0,0 L10,5 L0,10 z" fill="var(--color-fd-muted-foreground)" />
      </marker>
    </defs>
  );
}

function Figure({ caption, children, label }: { caption: string; label: string; children: React.ReactNode }) {
  return (
    <figure className="not-prose my-6 overflow-x-auto rounded-xl border border-fd-border bg-fd-background p-4">
      <div role="img" aria-label={label}>{children}</div>
      <figcaption className="mt-2 text-center text-xs text-fd-muted-foreground">{caption}</figcaption>
    </figure>
  );
}

export function SystemLandscape() {
  return (
    <Figure
      label="Lanskap sistem: TrakCare/HIS mengirim data ke Bridge PostgreSQL, Airflow memindahkan data ke Odoo ERP Parent dan Odoo Unit, Odoo Unit mengirim harga jual kembali ke TrakCare."
      caption="Ilustrasi konseptual (bukan screenshot aplikasi). Disusun dari README Airflow lokal dan kode odoo-revamp; topologi deploy aktual perlu dicek di server."
    >
      <svg viewBox="0 0 860 330" className="mx-auto w-full min-w-[640px] max-w-[860px]">
        <Defs />
        <Box x={20} y={30} w={190} h={70} title="TrakCare / HIS" sub="klinis, registrasi, billing pasien" tone="accent" />
        <Box x={20} y={130} w={190} h={60} title="Wipro / Dhealth / Andal" sub="HIS lama per unit (legacy)" tone="muted" />
        <Box x={330} y={30} w={200} h={70} title="Bridge PostgreSQL" sub="mst_* / trx_* staging" />
        <Box x={330} y={130} w={200} h={60} title="Airflow (A1/A2/A3)" sub="orkestrasi job harian" tone="muted" />
        <Box x={640} y={20} w={200} h={70} title="Odoo 16 ERP Parent" sub="master, eProc, konsolidasi" tone="accent" />
        <Box x={640} y={120} w={200} h={70} title="Odoo Unit (16 / 10)" sub="tarif, AR, stok, jurnal unit" tone="accent" />
        <Box x={640} y={240} w={200} h={60} title="NAS / file TXT" sub="harga jual & koleksi" tone="muted" />
        <Arrow d="M210,60 L328,60" label="master & transaksi" lx={270} ly={52} />
        <Arrow d="M210,160 L328,160" label="query API lama" lx={270} ly={152} />
        <Arrow d="M530,55 L638,55" label="A1 Parent" lx={585} ly={47} />
        <Arrow d="M530,85 L638,145" label="A2 Unit" lx={590} ly={125} />
        <Arrow d="M740,92 L740,118" />
        <Arrow d="M740,190 L740,238" label="PUT harga final" lx={800} ly={220} />
        <Arrow d="M640,280 L120,280 L120,102" label="TXT dibaca TrakCare (Odoo → TC)" lx={380} ly={272} />
      </svg>
    </Figure>
  );
}

export function PriceFormula() {
  return (
    <Figure
      label="Rumus harga jual final: base price atau harga tarif sumber, dikali depend rate jika ada dependency, lalu dikali satu ditambah markup rate, menghasilkan Fixed Selling Price."
      caption="Ilustrasi konseptual dari TariffPricelistFixed._compute_fixed_price_vals() (eproc/eproc_tc.py). Angka contoh sintetis."
    >
      <svg viewBox="0 0 860 200" className="mx-auto w-full min-w-[640px] max-w-[860px]">
        <Defs />
        <Box x={10} y={60} w={170} h={80} title="Harga dasar" sub="tariff.pricelist current/new" tone="accent" />
        <Box x={235} y={60} w={170} h={80} title="× Depend Rate" sub="tariff.dependency (opsional)" />
        <Box x={460} y={60} w={170} h={80} title="× (1 + Markup%)" sub="tariff.markup tier harga" />
        <Box x={685} y={60} w={165} h={80} title="Fixed Selling Price" sub="tariff.pricelist.fixed" tone="accent" />
        <Arrow d="M180,100 L233,100" />
        <Arrow d="M405,100 L458,100" />
        <Arrow d="M630,100 L683,100" />
        <text x={95} y={170} textAnchor="middle" fontSize={12} fill="var(--color-fd-foreground)">Rp100.000</text>
        <text x={320} y={170} textAnchor="middle" fontSize={12} fill="var(--color-fd-foreground)">× 120% = Rp120.000</text>
        <text x={545} y={170} textAnchor="middle" fontSize={12} fill="var(--color-fd-foreground)">× 1,25 = Rp150.000</text>
        <text x={767} y={170} textAnchor="middle" fontSize={12} fontWeight={600} fill="var(--color-fd-primary)">Rp150.000</text>
        <text x={430} y={30} textAnchor="middle" fontSize={13} fill="var(--color-fd-muted-foreground)">Contoh sintetis — tarif B bergantung ke tarif A, markup kategori 25%</text>
      </svg>
    </Figure>
  );
}
