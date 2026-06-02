/**
 * Checkpoint 2 visual review — atomic components in all states.
 * Visit /dev during development to verify palette alignment.
 */
import { BadgeChip } from "@/components/BadgeChip";
import { StatTile } from "@/components/StatTile";
import { StatTileRow } from "@/components/StatTileRow";
import { ConnectedItemRow } from "@/components/ConnectedItemRow";
import { PrimaryCTA } from "@/components/PrimaryCTA";
import { KeywordCard, TopicCard, GathaTile } from "@/components/ListCards";
import type { EntityKind } from "@/lib/types";

const KINDS: EntityKind[] = ["shastra", "gatha", "teeka", "bhaavarth", "kalash", "page", "topic", "keyword"];

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-12">
      <h2 className="mb-4 font-sans text-[length:var(--font-size-h2)] font-semibold text-foreground-muted uppercase tracking-widest">
        {title}
      </h2>
      {children}
    </section>
  );
}

export default function DevPage() {
  return (
    <main className="mx-auto max-w-[1200px] px-6 py-12">
      <h1 className="mb-10 font-serif-hindi text-[length:var(--font-size-display)] font-semibold text-foreground">
        Phase 2 — Component Gallery
      </h1>

      {/* BadgeChip */}
      <Section title="BadgeChip × 4 kinds × 2 sizes">
        <div className="flex flex-wrap gap-3">
          {KINDS.map((k) => (
            <BadgeChip key={k + "-md"} kind={k} size="md" />
          ))}
        </div>
        <div className="mt-3 flex flex-wrap gap-3">
          {KINDS.map((k) => (
            <BadgeChip key={k + "-sm"} kind={k} size="sm" />
          ))}
        </div>
        <div className="mt-3 flex flex-wrap gap-3">
          <BadgeChip kind="shastra" labelHi="कस्टम शास्त्र" labelEn="Custom Shastra" />
        </div>
      </Section>

      {/* StatTile */}
      <Section title="StatTile (single)">
        <div className="flex gap-3">
          <StatTile count={357} label="गाथाएँ" />
          <StatTile count={10} label="संबंध" />
          <StatTile count={0} label="विषय" />
        </div>
      </Section>

      {/* StatTileRow */}
      <Section title="StatTileRow (3-up)">
        <StatTileRow
          tiles={[
            { count: 357, label: "गाथाएँ" },
            { count: 12, label: "संबंध" },
            { count: 4, label: "विषय" },
          ]}
        />
      </Section>

      {/* ConnectedItemRow — link mode */}
      <Section title="ConnectedItemRow — link mode">
        <div className="flex max-w-md flex-col gap-2">
          {KINDS.map((k) => (
            <ConnectedItemRow
              key={k}
              kind={k}
              titleHi="तत्त्वार्थसूत्र"
              titleEn="Tattvartha Sutra"
              href="#"
            />
          ))}
        </div>
      </Section>

      {/* ConnectedItemRow — button mode */}
      <Section title="ConnectedItemRow — button mode">
        <div className="flex max-w-md flex-col gap-2">
          {KINDS.map((k) => (
            <ConnectedItemRow
              key={k}
              kind={k}
              titleHi="अनेकान्तवाद"
              onClick={() => {}}
            />
          ))}
        </div>
      </Section>

      {/* PrimaryCTA */}
      <Section title="PrimaryCTA">
        <div className="w-80 rounded-[var(--radius-md)] border border-border bg-surface py-4 shadow-node">
          <PrimaryCTA
            labelHi="विस्तार से पढ़ें"
            labelEn="Read More"
            href="#"
          />
        </div>
        <div className="mt-4 w-80 rounded-[var(--radius-md)] border border-border bg-surface py-4 shadow-node">
          <PrimaryCTA
            labelHi="ग्राफ में खोलें"
            labelEn="Open in Graph"
            href="#"
          />
        </div>
      </Section>

      {/* List cards */}
      <Section title="KeywordCard / TopicCard / GathaTile">
        <div className="grid grid-cols-3 gap-4">
          <KeywordCard
            kind="keyword"
            titleHi="अनेकान्तवाद"
            titleEn="Anekantavada"
            meta="जैन दर्शन का मूल सिद्धांत"
            count={42}
            href="#"
          />
          <TopicCard
            kind="topic"
            titleHi="तत्त्व विचार"
            titleEn="Tattva Vichar"
            meta="मूल विषय: आत्मा"
            count={128}
            href="#"
          />
          <GathaTile
            kind="gatha"
            titleHi="गाथा १.१"
            titleEn="Gatha 1.1"
            meta="तत्त्वार्थसूत्र"
            href="#"
          />
        </div>
      </Section>
    </main>
  );
}
