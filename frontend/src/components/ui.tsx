/** Small shared interface pieces. One visual language for the whole ground station. */
import { Circle, CircleCheck, CircleX, TriangleAlert, X } from 'lucide-react'
import {
  type ButtonHTMLAttributes,
  type ReactNode,
  useEffect,
  useId,
  useRef,
  useState,
} from 'react'

import type { CheckStatus } from '../lib/api'
import { useVehicle } from '../lib/store'

type Variant = 'primary' | 'secondary' | 'danger' | 'ghost'

const VARIANT: Record<Variant, string> = {
  primary: 'bg-brand text-on-brand hover:brightness-110 font-semibold',
  secondary: 'bg-surface-3 text-ink hover:brightness-125 border border-line',
  danger: 'bg-danger text-on-danger hover:brightness-110 font-semibold',
  ghost: 'text-ink hover:bg-surface-3',
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  small?: boolean
  icon?: ReactNode
  busy?: boolean
}

export function Button({
  variant = 'secondary',
  small,
  icon,
  busy,
  children,
  className = '',
  disabled,
  ...rest
}: ButtonProps) {
  return (
    <button
      type="button"
      disabled={disabled || busy}
      className={`inline-flex items-center justify-center gap-2 rounded-md transition
        duration-150 disabled:opacity-45 ${small ? 'min-h-9 px-2.5 text-[13px]' : 'min-h-11 px-4'}
        ${VARIANT[variant]} ${className}`}
      {...rest}
    >
      {busy ? <span className="size-4 animate-spin rounded-full border-2 border-current border-t-transparent" /> : icon}
      {children}
    </button>
  )
}

/**
 * A button that must be held to act. Used for commands that start motors or a
 * mission, so a stray click or tap cannot do it.
 */
export function HoldButton({
  onConfirm,
  holdMs = 800,
  variant = 'primary',
  icon,
  children,
  disabled,
  className = '',
  title,
}: {
  onConfirm: () => void
  holdMs?: number
  variant?: Variant
  icon?: ReactNode
  children: ReactNode
  disabled?: boolean
  className?: string
  title?: string
}) {
  const [holding, setHolding] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  const start = () => {
    if (disabled) return
    setHolding(true)
    timer.current = setTimeout(() => {
      setHolding(false)
      onConfirm()
    }, holdMs)
  }
  const cancel = () => {
    clearTimeout(timer.current)
    setHolding(false)
  }
  useEffect(() => () => clearTimeout(timer.current), [])

  return (
    <button
      type="button"
      disabled={disabled}
      title={title ?? 'Press and hold'}
      onPointerDown={start}
      onPointerUp={cancel}
      onPointerLeave={cancel}
      onKeyDown={(e) => (e.key === ' ' || e.key === 'Enter') && !e.repeat && start()}
      onKeyUp={cancel}
      onBlur={cancel}
      className={`relative inline-flex min-h-11 select-none items-center justify-center gap-2
        overflow-hidden rounded-md px-4 transition duration-150 disabled:opacity-45
        ${VARIANT[variant]} ${className}`}
    >
      <span
        aria-hidden
        className="absolute inset-y-0 left-0 bg-white/35"
        style={{
          width: holding ? '100%' : '0%',
          transition: holding ? `width ${holdMs}ms linear` : 'none',
        }}
      />
      <span className="relative inline-flex items-center gap-2">
        {icon}
        {children}
        <span className="text-[10px] font-normal uppercase tracking-wide opacity-70">hold</span>
      </span>
    </button>
  )
}

export function Panel({
  title,
  actions,
  children,
  className = '',
}: {
  title?: ReactNode
  actions?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={`rounded-lg border border-line bg-surface ${className}`}>
      {(title || actions) && (
        <header className="flex min-h-11 items-center justify-between gap-2 border-b border-line px-3">
          <h2 className="text-[13px] font-semibold uppercase tracking-wide text-muted">{title}</h2>
          <div className="flex items-center gap-1">{actions}</div>
        </header>
      )}
      <div className="p-3">{children}</div>
    </section>
  )
}

export function Field({
  label,
  hint,
  unit,
  children,
}: {
  label: string
  hint?: string
  unit?: string
  children: (id: string) => ReactNode
}) {
  const id = useId()
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-[12px] font-medium text-muted">
        {label}
        {unit && <span className="font-normal"> ({unit})</span>}
      </label>
      {children(id)}
      {hint && <p className="text-[11px] leading-snug text-muted">{hint}</p>}
    </div>
  )
}

const INPUT =
  'min-h-10 w-full rounded-md border border-line bg-surface-2 px-2.5 text-ink ' +
  'placeholder:text-muted disabled:opacity-50'

export function NumberField({
  label,
  unit,
  hint,
  value,
  onChange,
  min,
  max,
  step = 1,
  disabled,
}: {
  label: string
  unit?: string
  hint?: string
  value: number
  onChange: (v: number) => void
  min?: number
  max?: number
  step?: number
  disabled?: boolean
}) {
  // Keep what the user is typing; only commit real numbers.
  const [text, setText] = useState(String(value))
  useEffect(() => setText(String(value)), [value])
  return (
    <Field label={label} unit={unit} hint={hint}>
      {(id) => (
        <input
          id={id}
          type="number"
          inputMode="decimal"
          className={`${INPUT} num`}
          value={text}
          min={min}
          max={max}
          step={step}
          disabled={disabled}
          onChange={(e) => {
            setText(e.target.value)
            const v = Number(e.target.value)
            if (e.target.value !== '' && Number.isFinite(v)) onChange(v)
          }}
          onBlur={() => setText(String(value))}
        />
      )}
    </Field>
  )
}

export function TextField({
  label,
  value,
  onChange,
  hint,
  placeholder,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  hint?: string
  placeholder?: string
}) {
  return (
    <Field label={label} hint={hint}>
      {(id) => (
        <input
          id={id}
          className={INPUT}
          value={value}
          placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
    </Field>
  )
}

export function SelectField<T extends string | number>({
  label,
  value,
  onChange,
  options,
  hint,
}: {
  label: string
  value: T
  onChange: (v: T) => void
  options: { value: T; label: string }[]
  hint?: string
}) {
  return (
    <Field label={label} hint={hint}>
      {(id) => (
        <select
          id={id}
          className={INPUT}
          value={String(value)}
          onChange={(e) => {
            const picked = options.find((o) => String(o.value) === e.target.value)
            if (picked) onChange(picked.value)
          }}
        >
          {options.map((o) => (
            <option key={String(o.value)} value={String(o.value)}>
              {o.label}
            </option>
          ))}
        </select>
      )}
    </Field>
  )
}

export function Toggle({
  label,
  checked,
  onChange,
  hint,
}: {
  label: string
  checked: boolean
  onChange: (v: boolean) => void
  hint?: string
}) {
  return (
    <label className="flex min-h-11 cursor-pointer items-center justify-between gap-3">
      <span>
        <span className="block">{label}</span>
        {hint && <span className="block text-[11px] text-muted">{hint}</span>}
      </span>
      <input
        type="checkbox"
        role="switch"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="peer sr-only"
      />
      <span
        aria-hidden
        className="relative h-6 w-11 shrink-0 rounded-full bg-surface-3 transition
          peer-checked:bg-brand peer-focus-visible:outline-2 peer-focus-visible:outline-info
          after:absolute after:left-0.5 after:top-0.5 after:size-5 after:rounded-full
          after:bg-ink after:transition peer-checked:after:translate-x-5"
      />
    </label>
  )
}

const TONE = {
  good: 'bg-brand/15 text-brand border-brand/40',
  warn: 'bg-warn/15 text-warn border-warn/40',
  bad: 'bg-danger/15 text-danger border-danger/40',
  info: 'bg-info/15 text-info border-info/40',
  muted: 'bg-surface-3 text-muted border-line',
} as const

export function Badge({
  tone = 'muted',
  children,
  className = '',
}: {
  tone?: keyof typeof TONE
  children: ReactNode
  className?: string
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[11px]
        font-semibold uppercase tracking-wide ${TONE[tone]} ${className}`}
    >
      {children}
    </span>
  )
}

/** Status shown by shape and word as well as colour. */
export function StatusIcon({ status, size = 18 }: { status: CheckStatus; size?: number }) {
  if (status === 'pass') return <CircleCheck size={size} className="shrink-0 text-brand" aria-label="Passed" />
  if (status === 'warn') return <TriangleAlert size={size} className="shrink-0 text-warn" aria-label="Warning" />
  if (status === 'fail') return <CircleX size={size} className="shrink-0 text-danger" aria-label="Failed" />
  return <Circle size={size} className="shrink-0 text-muted" aria-label="Not confirmed" />
}

export function CheckRow({
  status,
  label,
  detail,
  action,
}: {
  status: CheckStatus
  label: string
  detail?: string
  action?: ReactNode
}) {
  return (
    <li className="flex items-start gap-2.5 py-1.5">
      <span className="mt-0.5">
        <StatusIcon status={status} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block leading-tight">{label}</span>
        {detail && <span className="block text-[12px] leading-snug text-muted">{detail}</span>}
      </span>
      {action}
    </li>
  )
}

export function Dialog({
  title,
  onClose,
  children,
  footer,
  wide,
}: {
  title: string
  onClose: () => void
  children: ReactNode
  footer?: ReactNode
  wide?: boolean
}) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    ref.current?.focus()
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onPointerDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        ref={ref}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`flex max-h-[90vh] w-full flex-col rounded-xl border border-line bg-surface
          shadow-2xl ${wide ? 'max-w-2xl' : 'max-w-md'}`}
      >
        <header className="flex items-center justify-between border-b border-line px-4 py-3">
          <h2 className="text-base font-semibold">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="grid size-9 place-items-center rounded-md hover:bg-surface-3"
          >
            <X size={18} />
          </button>
        </header>
        <div className="scroll p-4">{children}</div>
        {footer && <footer className="flex justify-end gap-2 border-t border-line px-4 py-3">{footer}</footer>}
      </div>
    </div>
  )
}

const TOAST_TONE = {
  info: 'border-info/60',
  good: 'border-brand/60',
  warn: 'border-warn/60',
  bad: 'border-danger',
} as const

export function Toasts() {
  const toasts = useVehicle((s) => s.toasts)
  const dismiss = useVehicle((s) => s.dismiss)
  return (
    <div aria-live="polite" className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-80 flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`pointer-events-auto flex items-start gap-2 rounded-lg border-l-4 bg-surface-2
            px-3 py-2.5 shadow-xl ${TOAST_TONE[t.tone]}`}
        >
          <span className="flex-1 text-[13px] leading-snug">{t.text}</span>
          <button type="button" aria-label="Dismiss" onClick={() => dismiss(t.id)} className="text-muted hover:text-ink">
            <X size={16} />
          </button>
        </div>
      ))}
    </div>
  )
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-line p-6 text-center">
      <p className="font-medium">{title}</p>
      {children && <p className="mx-auto mt-1 max-w-md text-[13px] text-muted">{children}</p>}
    </div>
  )
}

export function Stat({
  label,
  value,
  unit,
  tone,
}: {
  label: string
  value: ReactNode
  unit?: string
  tone?: 'good' | 'warn' | 'bad'
}) {
  const color = tone === 'bad' ? 'text-danger' : tone === 'warn' ? 'text-warn' : 'text-ink'
  return (
    <div className="min-w-0">
      <div className="truncate text-[10.5px] font-medium uppercase tracking-wider text-muted">{label}</div>
      <div className={`num text-lg font-semibold leading-tight ${color}`}>
        {value}
        {unit && <span className="ml-0.5 text-[11px] font-normal text-muted">{unit}</span>}
      </div>
    </div>
  )
}
