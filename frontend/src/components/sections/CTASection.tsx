import { motion } from "framer-motion";
import { ArrowRight, Sparkles } from "lucide-react";

export const CTASection = () => {
  return (
    <section className="py-20 sm:py-32 bg-background relative overflow-hidden">
      {/* Background */}
      <div className="absolute inset-0 gradient-primary opacity-[0.03]" />
      <div className="absolute inset-0">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] bg-primary/10 rounded-full blur-3xl animate-pulse" />
        <div className="absolute top-20 left-20 w-32 h-32 bg-accent/10 rounded-full blur-2xl animate-bounce" style={{ animationDelay: "1s" }} />
        <div className="absolute bottom-20 right-20 w-48 h-48 bg-primary/8 rounded-full blur-2xl animate-bounce" style={{ animationDelay: "3s" }} />
      </div>

      {/* Floating Elements */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        transition={{ duration: 0.8, delay: 0.5 }}
        className="absolute top-16 left-16 hidden lg:block"
      >
        <div className="glass p-3 rounded-xl shadow-card animate-float">
          <Sparkles className="w-6 h-6 text-primary" />
        </div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: -20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        transition={{ duration: 0.8, delay: 0.7 }}
        className="absolute bottom-16 right-16 hidden lg:block"
      >
        <div className="glass p-3 rounded-xl shadow-card animate-float" style={{ animationDelay: "2s" }}>
          <ArrowRight className="w-6 h-6 text-accent" />
        </div>
      </motion.div>

      <div className="container mx-auto px-4 sm:px-6 relative z-10">
        <motion.div
          initial={{ opacity: 0, y: 40 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
          className="max-w-4xl mx-auto text-center"
        >
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full glass shadow-soft mb-8">
            <Sparkles className="w-4 h-4 text-primary" />
            <span className="text-sm font-medium text-foreground">Найдите компанию</span>
          </div>

          <h2 className="text-3xl sm:text-4xl md:text-5xl lg:text-6xl font-bold text-foreground mb-6">
            Начните поиск прямо сейчас
          </h2>

          <p className="text-lg sm:text-xl text-muted-foreground mb-10 max-w-2xl mx-auto">
            Введите УНП или название компании и получите полную информацию из базы данных ЕГР
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <button
              onClick={() => {
                window.scrollTo({ top: 0, behavior: 'smooth' });
              }}
              className="gradient-primary text-primary-foreground shadow-soft hover:shadow-glow transition-all px-8 py-6 text-lg animate-glow dark:shadow-glow dark:hover:shadow-xl inline-flex items-center gap-2"
            >
              Начать поиск
              <ArrowRight className="w-5 h-5" />
            </button>
          </div>
        </motion.div>
      </div>
    </section>
  );
};
