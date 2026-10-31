/** Company updates shown at /news, newest first. Each paragraph is plain text. */
export type NewsPost = {
  slug: string;
  title: string;
  date: string; // YYYY-MM-DD
  time: string; // shown as written, e.g. "10:47 AM PT"
  summary: string;
  body: string[];
};

export const NEWS: NewsPost[] = [
  {
    slug: "backed-by-y-combinator",
    title: "OpenScientist raises $125,000 from Y Combinator",
    date: "2026-10-30",
    time: "10:47 AM PT",
    summary: "Along with more than $200,000 in compute and credits, we're starting to onboard our waitlist and open access to more researchers.",
    body: [
      "We're excited to share that OpenScientist has raised $125,000 from Y Combinator, along with more than $200,000 in compute and credits.",
      "We feel very fortunate, and we're deeply thankful to YC for backing us. Running real science takes real compute, and this support lets us give far more people access to it.",
      "Over the coming weeks we'll start onboarding people from our waitlist, which has grown much larger than we expected. We'll also be introducing better tiers and opening access to more users, researchers and labs.",
      "We hope to be fully open by the end of November.",
      "Thank you to everyone who joined the waitlist and has been patient with us. We can't wait to see what you'll discover.",
    ],
  },
];

export function newsPost(slug: string) {
  return NEWS.find((p) => p.slug === slug);
}

export function formatNewsDate(date: string) {
  return new Date(`${date}T12:00:00Z`).toLocaleDateString("en-US", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
    timeZone: "UTC",
  });
}
