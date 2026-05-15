export default function AboutPage() {
  return (
    <div className="max-w-[720px] mx-auto space-y-6">
      {/* Mission */}
      <div className="rounded-[var(--radius-md)] border border-border bg-surface p-8 shadow-node">
        <h1 className="font-serif-hindi text-[length:var(--font-size-h1)] font-semibold text-foreground">
          परिचय
        </h1>
        <div className="mt-4 space-y-4 font-serif-hindi text-[length:var(--font-size-body)] leading-relaxed text-foreground">
          <p>
            जैन ज्ञान कोष एक संरचित ज्ञान-खोज प्रणाली है जो जैन आगमों, ग्रंथों और शास्त्रीय साहित्य के लिए एक सुलभ एवं व्यवस्थित अन्वेषण परत प्रदान करती है।
            इसका उद्देश्य प्राचीन ज्ञान को आधुनिक तकनीक के माध्यम से विद्वानों, साधकों और जिज्ञासुओं तक सरलता से पहुँचाना है।
          </p>
          <p>
            इस प्रणाली में शब्दकोश, विषय-सूची, गाथाएँ और शास्त्र-संदर्भ परस्पर जुड़े हुए ग्राफ रूप में उपस्थित हैं। प्रत्येक शब्द, विषय और स्रोत के बीच
            सम्बन्ध स्थापित कर यह कोष जैन साहित्य की गहराइयों को एक नई दृष्टि से प्रस्तुत करता है।
          </p>
          <p>
            हमारा लक्ष्य है कि जैन आगम-साहित्य की बहुभाषीय विरासत — संस्कृत, प्राकृत एवं हिन्दी में — डिजिटल युग में संरक्षित, सुलभ और खोजयोग्य बने।
            यह परियोजना मुक्त-स्रोत डेटा एवं समुदाय के सहयोग से निरन्तर विकसित हो रही है।
          </p>
        </div>
      </div>

      {/* Sources */}
      <div className="rounded-[var(--radius-md)] border border-border bg-surface p-8 shadow-node">
        <h2 className="font-serif-hindi text-[length:var(--font-size-h2)] font-semibold text-foreground">
          स्रोत और आभार
        </h2>
        <div className="mt-4 space-y-4">
          {/* Source 1 */}
          <div className="rounded-[var(--radius-md)] border border-border bg-surface p-4">
            <p className="font-serif-hindi text-[length:var(--font-size-body)] font-semibold text-foreground">
              जैनकोश
            </p>
            <a
              href="https://jainkosh.org"
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-accent hover:underline"
            >
              jainkosh.org
            </a>
            <p className="mt-1 text-sm text-foreground-muted">Creative Commons license</p>
          </div>

          {/* Source 2 */}
          <div className="rounded-[var(--radius-md)] border border-border bg-surface p-4">
            <p className="font-serif-hindi text-[length:var(--font-size-body)] font-semibold text-foreground">
              Nikky Jain Agam
            </p>
            <a
              href="https://nikkyjain.github.io"
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-accent hover:underline"
            >
              nikkyjain.github.io
            </a>
            <p className="mt-1 text-sm text-foreground-muted">Open source</p>
          </div>

          {/* Source 3 */}
          <div className="rounded-[var(--radius-md)] border border-border bg-surface p-4">
            <p className="font-serif-hindi text-[length:var(--font-size-body)] font-semibold text-foreground">
              व्याकरण विश्लेषण
            </p>
            <p className="text-sm text-foreground-muted">Vyakaran Vishleshan</p>
            <p className="mt-1 text-sm text-foreground-muted">Original research corpus</p>
          </div>
        </div>
      </div>

      {/* Tech stack */}
      <div className="rounded-[var(--radius-md)] border border-border bg-surface px-8 py-6 shadow-node">
        <p className="text-sm font-medium text-foreground-muted">Tech Stack</p>
        <p className="mt-2 text-sm text-foreground-muted">
          FastAPI · PostgreSQL · MongoDB · Neo4j · Next.js 16 · Tailwind 4
        </p>
      </div>
    </div>
  );
}
