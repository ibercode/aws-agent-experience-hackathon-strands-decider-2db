// Persisted event names remain compatible; product labels use the current roles.
export const productText = (text: string) => text
  .replace(/\btrainees\b/gi, 'controllers')
  .replace(/\btrainee\b/gi, 'controller')
  .replace(/\binstructor\b/gi, 'ATC assistant')
  .replace(/\bcoaching\b/gi, 'advisory');
export const actorLabel = (actor: string) => ({
  trainee: 'ATC', controller: 'ATC', pilot: 'Pilot', instructor: 'ATC assistant',
  assistant: 'ATC assistant', simulator: 'Simulator', decider: 'Decider',
  bedrock: 'Bedrock', tool: 'Tool', system: 'System',
}[actor] || actor.charAt(0).toUpperCase() + actor.slice(1));
