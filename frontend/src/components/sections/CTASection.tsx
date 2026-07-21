import { motion } from "framer-motion";
import { ArrowUpRight, Building2, Network, Search, ShieldCheck } from "lucide-react";

const resultItems = [
  { icon: Building2, label: "Карточка компании", value: "готова" },
  { icon: Network, label: "Карта связей", value: "3 связи" },
  { icon: ShieldCheck, label: "Проверка сигналов", value: "завершена" },
];

export const CTASection = () => {
  const handleScrollToSearch = () => {
    const element = document.getElementById("hero-search");
    if (element) {
      element.scrollIntoView({ behavior: "smooth", block: "center" });
      window.setTimeout(() => element.querySelector("input")?.focus(), 400);
      return;
    }

    window.scrollTo({ top: 0, left: 0, behavior: "smooth" });
  };

  return (
    <section className="landing-section relative overflow-hidden px-4 py-20 sm:px-6 sm:py-28">
      <div className="container relative z-10 mx-auto max-w-7xl">
        <motion.div
          initial={{ opacity: 0, y: 26 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.55 }}
          className="cta-panel"
        >
          <div className="cta-panel-grid" aria-hidden="true" />
          <div className="cta-panel-orb" aria-hidden="true" />

          <div className="relative z-10 grid items-center gap-10 lg:grid-cols-[1fr_0.8fr] lg:gap-16">
            <div>
              <div className="eyebrow mb-6">Начните с одной компании</div>
              <h2 className="max-w-3xl text-3xl font-extrabold leading-tight text-foreground sm:text-4xl lg:text-5xl">
                Решение начинается
                <span className="block text-gradient">с правильной проверки</span>
              </h2>
              <p className="mt-5 max-w-2xl text-base leading-7 text-muted-foreground sm:text-lg">
                Введите УНП или название — Tendex соберёт профиль и покажет, на что стоит обратить внимание.
              </p>

              <button
                type="button"
                onClick={handleScrollToSearch}
                className="gradient-primary group mt-8 inline-flex items-center gap-2 rounded-2xl px-6 py-3.5 text-sm font-semibold text-primary-foreground shadow-soft hover:-translate-y-0.5 hover:shadow-glow"
              >
                <Search className="h-4 w-4" />
                Проверить компанию
                <ArrowUpRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
              </button>
            </div>

            <div className="cta-result-stack">
              <div className="cta-result-head">
                <span><i /> Анализ завершён</span>
                <strong>ООО «ИНФУБЕРИ»</strong>
              </div>
              {resultItems.map((item, index) => (
                <motion.div
                  key={item.label}
                  initial={{ opacity: 0, x: 16 }}
                  whileInView={{ opacity: 1, x: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.4, delay: 0.18 + index * 0.08 }}
                  className="cta-result-item"
                >
                  <item.icon className="h-4 w-4 text-primary" />
                  <span>{item.label}</span>
                  <strong>{item.value}</strong>
                </motion.div>
              ))}
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
};
