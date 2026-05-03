import { motion } from "framer-motion";
import { Search, Sparkles } from "lucide-react";

export const CTASection = () => {
  const handleScrollToTop = () => {
    window.scrollTo({ top: 0, left: 0, behavior: "smooth" });
  };

  return (
    <section className="relative overflow-hidden px-4 py-20 sm:px-6 sm:py-28">
      <div className="absolute inset-0">
        <div className="absolute left-1/2 top-1/2 h-[28rem] w-[28rem] -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary/10 blur-3xl" />
      </div>

      <div className="container relative z-10 mx-auto max-w-5xl">
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.55 }}
          className="surface-card shadow-glow rounded-[2.2rem] px-6 py-10 text-center sm:px-10 sm:py-14"
        >
          <div className="eyebrow mb-6">
            <Sparkles className="h-4 w-4 text-accent" />
            Начните поиск
          </div>

          <h2 className="mx-auto max-w-3xl text-3xl font-extrabold leading-tight text-foreground sm:text-4xl lg:text-5xl">
            Найдите компанию по УНП
            <span className="block text-gradient">или названию</span>
          </h2>

          <p className="mx-auto mt-5 max-w-2xl text-base leading-7 text-muted-foreground sm:text-lg">
            Откройте карточку организации, проверьте основные сведения, историю
            названий, адреса и связанные данные из сервиса ЕГР.
          </p>

          <div className="mt-8 flex items-center justify-center">
            <button
              type="button"
              onClick={handleScrollToTop}
              className="gradient-primary inline-flex items-center gap-2 rounded-2xl px-6 py-3.5 text-sm font-semibold text-primary-foreground shadow-soft hover:-translate-y-0.5 hover:shadow-glow"
            >
              <Search className="h-4 w-4" />
              Начать поиск
            </button>
          </div>
        </motion.div>
      </div>
    </section>
  );
};
