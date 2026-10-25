import { STEPS, currentStep, type Stage } from './status';

/** The order's route as a sequence of stops, with the current stop marked for assistive technology. */
export function OrderRoute({ stage }: { stage: Stage }) {
  const current = currentStep(stage);
  return (
    <ol className={`route route-${stage}`}>
      {STEPS.map((step, index) => {
        const state = index < current || stage === 'fulfilled' ? 'done' : index === current ? 'current' : 'ahead';
        return (
          <li key={step} className={`stop stop-${state}`} aria-current={index === current ? 'step' : undefined}>
            <span className="stop-mark" aria-hidden="true" />
            <span className="stop-name">{step}</span>
          </li>
        );
      })}
    </ol>
  );
}
