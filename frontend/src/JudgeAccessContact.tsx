const judgeEmail = 'decider@ibercode.com';
const requestSubject = encodeURIComponent('AWS hackathon judge — Live Demo access request');

export function JudgeAccessContact({ className = '' }: { className?: string }) {
  return <p className={`judge-access-contact ${className}`}>
    <strong>AWS hackathon judges:</strong> request a Live Demo invitation at{' '}
    <a href={`mailto:${judgeEmail}?subject=${requestSubject}`}>{judgeEmail}</a>.
  </p>;
}
