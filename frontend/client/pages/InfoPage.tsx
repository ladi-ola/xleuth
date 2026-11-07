import { AppShell } from "@/components/xleuth/AppShell";

type InfoSection = {
  title: string;
  body: string;
};

export function InfoPage({
  title,
  intro,
  sections,
}: {
  title: string;
  intro: string;
  sections: InfoSection[];
}) {
  return (
    <AppShell>
      <article className="xleuth-info-page">
        <h1>{title}</h1>
        <section className="terminal-card"><p>{intro}</p></section>
        {sections.map((section) => (
          <section className="terminal-card" key={section.title}>
            <h2>{section.title}</h2>
            <p>{section.body}</p>
          </section>
        ))}
      </article>
    </AppShell>
  );
}
