import { motion, useReducedMotion } from "framer-motion";

const dataCards = [
  { label: "UNP", value: "190247488", className: "left-[7%] top-[24%]" },
  { label: "API", value: "24 ms", className: "right-[9%] top-[30%]" },
  { label: "SYNC", value: "99.9%", className: "left-[12%] bottom-[24%]" },
  { label: "ES", value: "1.6M", className: "right-[14%] bottom-[22%]" },
];

const lanes = Array.from({ length: 9 }, (_, index) => index);

export const AnimatedHeroBackdrop = () => {
  const shouldReduceMotion = useReducedMotion();

  return (
    <div aria-hidden="true" className="absolute inset-0 overflow-hidden">
      <div className="absolute inset-0 registry-grid opacity-70" />
      <div className="absolute inset-0 registry-vignette" />

      <motion.div
        className="absolute left-1/2 top-1/2 h-[36rem] w-[36rem] -translate-x-1/2 -translate-y-1/2 rounded-full border border-primary/10"
        animate={shouldReduceMotion ? undefined : { rotate: 360 }}
        transition={{ duration: 52, ease: "linear", repeat: Infinity }}
      >
        <div className="absolute left-1/2 top-0 h-2 w-2 -translate-x-1/2 rounded-full bg-primary shadow-glow" />
        <div className="absolute bottom-12 left-10 h-1.5 w-1.5 rounded-full bg-accent" />
        <div className="absolute right-16 top-20 h-1.5 w-1.5 rounded-full bg-primary/80" />
      </motion.div>

      <motion.div
        className="absolute left-1/2 top-1/2 h-[25rem] w-[25rem] -translate-x-1/2 -translate-y-1/2 rounded-full border border-accent/15"
        animate={shouldReduceMotion ? undefined : { rotate: -360 }}
        transition={{ duration: 38, ease: "linear", repeat: Infinity }}
      />

      <div className="absolute inset-x-0 top-[18%] mx-auto h-56 max-w-5xl overflow-hidden opacity-70">
        {lanes.map((lane) => (
          <motion.div
            key={lane}
            className="absolute h-px w-44 bg-gradient-to-r from-transparent via-primary/35 to-transparent"
            style={{ top: `${lane * 24}px`, left: `${(lane % 3) * 18}%` }}
            animate={shouldReduceMotion ? undefined : { x: ["-30%", "140%"], opacity: [0, 1, 0] }}
            transition={{
              duration: 4.5 + lane * 0.18,
              delay: lane * 0.22,
              ease: "easeInOut",
              repeat: Infinity,
            }}
          />
        ))}
      </div>

      <motion.div
        className="absolute inset-y-0 left-1/2 w-px bg-gradient-to-b from-transparent via-primary/40 to-transparent"
        animate={shouldReduceMotion ? undefined : { x: ["-42vw", "42vw"], opacity: [0, 1, 0] }}
        transition={{ duration: 7, ease: "easeInOut", repeat: Infinity, repeatDelay: 1.2 }}
      />

      {dataCards.map((card, index) => (
        <motion.div
          key={card.label}
          className={`hidden lg:block absolute ${card.className}`}
          initial={{ opacity: 0, y: 14, scale: 0.96 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.7, delay: 0.35 + index * 0.12 }}
        >
          <motion.div
            className="glass rounded-xl px-4 py-3 shadow-card"
            animate={shouldReduceMotion ? undefined : { y: [0, -8, 0] }}
            transition={{ duration: 6 + index, ease: "easeInOut", repeat: Infinity }}
          >
            <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              {card.label}
            </div>
            <div className="font-mono text-sm text-foreground">{card.value}</div>
          </motion.div>
        </motion.div>
      ))}
    </div>
  );
};
