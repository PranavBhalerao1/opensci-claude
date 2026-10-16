/**
 * The paid plans. Prices match the Stripe products (looked up by `lookupKey`), and
 * `credits` is what each billing period grants. One credit is one cent of metered
 * compute (model time and cloud GPUs), so the backend stores credits / 100 as
 * subscriptions.credits_usd and counts spend against it.
 */
export type PlanId = "light" | "intensive" | "ultra";

export interface Plan {
  id: PlanId;
  name: string;
  price: number; // USD per month
  credits: number; // per month
  lookupKey: string; // Stripe price lookup key
  tagline: string;
  features: string[];
}

export const CREDITS_PER_USD = 100;

export const PLANS: Plan[] = [
  {
    id: "light",
    name: "Light",
    price: 80,
    credits: 4_000,
    lookupKey: "openscientist_light_monthly",
    tagline: "For trying research on your own questions.",
    features: [
      "4,000 credits every month",
      "All seven stages, question to paper",
      "Private cloud sandbox per investigation",
      "Cloud GPUs, metered by the second",
      "Guided or autonomous runs",
    ],
  },
  {
    id: "intensive",
    name: "Intensive",
    price: 350,
    credits: 18_000,
    lookupKey: "openscientist_intensive_monthly",
    tagline: "For researchers running studies every week.",
    features: [
      "18,000 credits every month",
      "Everything in Light",
      "4.5× the credits of Light",
      "Room for bigger literature reviews and GPU jobs",
    ],
  },
  {
    id: "ultra",
    name: "Ultra",
    price: 950,
    credits: 50_000,
    lookupKey: "openscientist_ultra_monthly",
    tagline: "For heavy compute and long autonomous runs.",
    features: [
      "50,000 credits every month",
      "Everything in Intensive",
      "12.5× the credits of Light",
      "Built for model training and long autonomous runs",
    ],
  },
];

export const LAB_FEATURES = [
  "Credits pooled across your team",
  "Volume pricing and invoicing",
  "Onboarding with the OpenScientist team",
  "Custom credit limits per member",
];

export const planById = (id: string | null | undefined) => PLANS.find((p) => p.id === id);
export const planByLookupKey = (key: string | null | undefined) => PLANS.find((p) => p.lookupKey === key);

/** USD of metered compute → credits, rounded down so the balance never overstates. */
export const toCredits = (usd: number) => Math.floor(usd * CREDITS_PER_USD + 1e-9);
