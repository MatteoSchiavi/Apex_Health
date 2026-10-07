/** Registry-independent rendering contract. Text uses the application's locale catalog. */
export type EducationText = {
  key: string;
  values?: Record<string, string | number>;
};

export type EducationFact = {
  label: EducationText;
  display: EducationText | {
    value: number;
    unit: string;
    metric: string;
    signed?: boolean;
  };
};

export type MetricSemantics = "measured" | "apex_derived" | "provider_proprietary";

export interface MetricExplanation {
  identity: { metric: string; label: EducationText };
  semanticType: MetricSemantics;
  heuristic?: boolean;
  context: EducationFact[];
  /** Only actual persisted calculation inputs, never surrounding observations or possible influences. */
  actualCalculation?: { asOf: string; contributors: EducationFact[] };
  definition: EducationText;
  whyItMatters?: EducationText;
  knownInfluences: EducationText[];
  actionableFactors: EducationText[];
  methodology: EducationText[];
  provenance: EducationText[];
  calculationDetails?: EducationFact[];
  limitations: EducationText[];
}
