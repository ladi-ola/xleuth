import { Layout } from "@/components/xleuth/Layout";

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
    <Layout width="md">
      <div className="flex flex-col gap-4 px-4 pt-4 pb-8 md:px-0 md:pt-0 md:pb-0">
        <h1 className="text-lg font-semibold text-neutral-100">{title}</h1>
        <div className="rounded-xl border-[0.4px] border-neutral-600 bg-neutral-900 p-4">
          <p className="text-xs leading-5 text-neutral-300">{intro}</p>
        </div>
        <div className="flex flex-col gap-3">
          {sections.map((section) => (
            <section
              key={section.title}
              className="rounded-xl border-[0.4px] border-neutral-600 bg-neutral-900 p-4"
            >
              <h2 className="text-sm font-medium text-neutral-100">{section.title}</h2>
              <p className="mt-2 text-xs leading-5 text-neutral-400">{section.body}</p>
            </section>
          ))}
        </div>
      </div>
    </Layout>
  );
}
