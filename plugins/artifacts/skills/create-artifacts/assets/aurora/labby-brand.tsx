"use client"

import * as React from "react"

export interface LabbyMarkProps extends React.SVGAttributes<SVGSVGElement> {
  size?: number
}

export function LabbyMark({ size = 32, style, ...props }: LabbyMarkProps) {
  return (
    <svg
      width={size}
      height={Math.round(size * 1.06)}
      viewBox="0 0 48 51"
      fill="none"
      aria-label="Labby mark"
      style={{ flexShrink: 0, ...style }}
      {...props}
    >
      <path d="M8 13L24 7L40 13L24 19Z" fill="var(--aurora-border-strong)" opacity="0.96" />
      <path d="M8 21L24 15L40 21L24 27Z" fill="var(--aurora-accent-deep)" opacity="0.92" />
      <path d="M8 29L24 23L40 29L24 35Z" fill="var(--aurora-accent-primary)" opacity="0.88" />
      <path d="M8 37L24 31L40 37L24 43Z" fill="var(--aurora-accent-strong)" opacity="0.9" />
    </svg>
  )
}

export interface LabbyWordmarkProps extends React.HTMLAttributes<HTMLSpanElement> {
  fontSize?: number
}

export interface AuroraWordmarkProps extends React.HTMLAttributes<HTMLSpanElement> {
  fontSize?: number
}

export function LabbyWordmark({ fontSize = 30, style, ...props }: LabbyWordmarkProps) {
  return (
    <span
      aria-label="Labby"
      style={{
        display: "inline-flex",
        alignItems: "baseline",
        fontFamily: "var(--aurora-font-display, Inter, sans-serif)",
        fontSize,
        fontWeight: 800,
        letterSpacing: "-0.042em",
        lineHeight: 0.96,
        userSelect: "none",
        color: "var(--aurora-text-primary)",
        ...style,
      }}
      {...props}
    >
      <span>Lab</span>
      <span style={{ color: "var(--aurora-accent-primary)" }}>by</span>
    </span>
  )
}

export function AuroraWordmark({ fontSize = 30, style, ...props }: AuroraWordmarkProps) {
  return (
    <span
      aria-label="Aurora"
      style={{
        display: "inline-flex",
        alignItems: "baseline",
        fontFamily: "var(--aurora-font-display, Inter, sans-serif)",
        fontSize,
        fontWeight: 800,
        letterSpacing: 0,
        lineHeight: 0.96,
        userSelect: "none",
        color: "var(--aurora-text-primary)",
        ...style,
      }}
      {...props}
    >
      <span aria-hidden="true">Aur</span>
      <span aria-hidden="true" style={{ color: "var(--aurora-accent-primary)" }}>ora</span>
    </span>
  )
}

export interface LabbyLockupProps extends React.HTMLAttributes<HTMLDivElement> {
  markSize?: number
  wordmarkSize?: number
  wordmark?: React.ReactNode
  subtitle?: React.ReactNode
}

export function LabbyLockup({
  markSize = 34,
  wordmarkSize = 28,
  wordmark,
  subtitle = "Aurora DS",
  style,
  ...props
}: LabbyLockupProps) {
  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 12,
        ...style,
      }}
      {...props}
    >
      <LabbyMark size={markSize} />
      <div style={{ display: "grid", gap: 2 }}>
        {wordmark ?? <LabbyWordmark fontSize={wordmarkSize} />}
        <span
          className="aurora-text-eyebrow"
          style={{
            margin: 0,
            color: "var(--aurora-text-muted)",
          }}
        >
          {subtitle}
        </span>
      </div>
    </div>
  )
}

export default LabbyLockup
