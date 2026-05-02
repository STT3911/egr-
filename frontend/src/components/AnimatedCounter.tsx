import { animate, useInView, useReducedMotion } from "framer-motion";
import { useEffect, useRef, useState } from "react";

type AnimatedCounterProps = {
  value: number;
  suffix?: string;
  prefix?: string;
  decimals?: number;
  duration?: number;
};

export const AnimatedCounter = ({
  value,
  suffix = "",
  prefix = "",
  decimals = 0,
  duration = 1.4,
}: AnimatedCounterProps) => {
  const ref = useRef<HTMLSpanElement>(null);
  const isInView = useInView(ref, { once: true, margin: "-40px" });
  const shouldReduceMotion = useReducedMotion();
  const [current, setCurrent] = useState(shouldReduceMotion ? value : 0);

  useEffect(() => {
    if (!isInView) return;
    if (shouldReduceMotion) {
      setCurrent(value);
      return;
    }

    const controls = animate(0, value, {
      duration,
      ease: [0.22, 1, 0.36, 1],
      onUpdate: setCurrent,
    });

    return () => controls.stop();
  }, [duration, isInView, shouldReduceMotion, value]);

  const formatted = current.toLocaleString("ru-RU", {
    maximumFractionDigits: decimals,
    minimumFractionDigits: decimals,
  });

  return (
    <span ref={ref}>
      {prefix}
      {formatted}
      {suffix}
    </span>
  );
};
