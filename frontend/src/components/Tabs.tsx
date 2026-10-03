import { useId, type KeyboardEvent } from "react";
export function Tabs<T extends string>({
  value,
  onChange,
  options,
  label,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: string }[];
  label: string;
}) {
  const id = useId();
  function onKey(e: KeyboardEvent<HTMLButtonElement>, index: number) {
    let next = index;
    if (e.key === "ArrowRight") next = (index + 1) % options.length;
    else if (e.key === "ArrowLeft")
      next = (index - 1 + options.length) % options.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = options.length - 1;
    else return;
    e.preventDefault();
    onChange(options[next].value);
    document.getElementById(id + "-" + next)?.focus();
  }
  return (
    <div role="tablist" aria-label={label} className="tabs">
      {options.map((o, index) => (
        <button
          key={o.value}
          id={id + "-" + index}
          type="button"
          role="tab"
          aria-selected={value === o.value}
          tabIndex={value === o.value ? 0 : -1}
          onKeyDown={(e) => onKey(e, index)}
          onClick={() => onChange(o.value)}
          className="tab"
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
