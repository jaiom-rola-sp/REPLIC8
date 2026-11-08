import './brand.css';

// The homepage mark is the canonical identity throughout the app.
export function BrandMark({ small = false, size, className = '' }) {
  return (
    <svg
      className={`brand-symbol${small ? ' small' : ''}${className ? ` ${className}` : ''}`}
      viewBox="0 0 64 32"
      fill="none"
      aria-hidden="true"
      focusable="false"
      style={size ? { width: size, height: size / 2 } : undefined}
    >
      <path
        d="M32 16C8-15 3 39 26 22L38 10C61-7 56 47 32 16Z"
        stroke="currentColor"
        strokeWidth="4"
      />
    </svg>
  );
}

export default function BrandLogo() {
  return <span className="replic8-logo"><BrandMark /><span>REPLIC8</span></span>;
}
