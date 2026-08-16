const SECTIONS = [
  {
    heading: "What we send",
    body: "Property attributes such as address, type, and bedrooms; rent figures and dates; and the lease document text you submit for audit.",
  },
  {
    heading: "Who processes it",
    body: "Anthropic, with an OpenAI backup, processes this information on our behalf via our compliance service.",
  },
  {
    heading: "What we never send",
    body: "Tenant names, emails, phone numbers, and co-tenant details are never sent as part of the structured data we assemble - property attributes, rent figures, dates. Lease documents you upload for audit are sent as-is, though, so any personal details written in the document itself will still reach the provider.",
  },
  {
    heading: "About the results",
    body: "Results are general information, not legal advice.",
  },
];

/** The AI features disclosure, shown before a landlord can enable any AI feature. */
export function AiDisclosure() {
  return (
    <div>
      <h2 className="font-semibold text-text">AI features disclosure</h2>
      <div className="mt-3 space-y-3">
        {SECTIONS.map((section) => (
          <div key={section.heading}>
            <h3 className="text-sm font-medium text-text">{section.heading}</h3>
            <p className="text-sm text-muted">{section.body}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
