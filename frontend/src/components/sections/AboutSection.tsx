import { motion } from "framer-motion";
import { CheckCircle2 } from "lucide-react";

const benefits = [
  "Актуальные данные из официального реестра ЕГР",
  "Высокая скорость поиска и обработки запросов",
  "Надежное хранение и защита данных",
  "Интеграция через REST API",
  "Управление правами доступа команды",
  "Журнал всех действий и изменений"
];

export const AboutSection = () => {
  return (
    <section id="about" className="py-20 sm:py-32 bg-secondary/30 relative overflow-hidden">
      {/* Background Elements */}
      <div className="absolute inset-0">
        <div className="absolute top-0 right-0 w-96 h-96 rounded-full blur-3xl animate-pulse dark:opacity-20" style={{
          backgroundColor: 'hsl(var(--primary) / 0.05)'
        }} />
        <div className="absolute bottom-0 left-0 w-72 h-72 rounded-full blur-3xl animate-pulse dark:opacity-25" style={{
          backgroundColor: 'hsl(var(--accent) / 0.04)',
          animationDelay: "2s"
        }} />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[400px] h-[400px] rounded-full blur-3xl dark:opacity-15" style={{
          backgroundColor: 'hsl(var(--primary) / 0.03)'
        }} />
        <div className="absolute top-20 left-10 w-24 h-24 rounded-full blur-xl animate-bounce dark:opacity-30" style={{
          backgroundColor: 'hsl(var(--accent) / 0.06)',
          animationDelay: "1s"
        }} />
        <div className="absolute bottom-20 right-10 w-32 h-32 rounded-full blur-xl animate-bounce dark:opacity-25" style={{
          backgroundColor: 'hsl(var(--primary) / 0.05)',
          animationDelay: "3s"
        }} />
      </div>

      <div className="container mx-auto px-4 sm:px-6 relative z-10">
        <div className="grid lg:grid-cols-2 gap-12 lg:gap-20 items-center">
          {/* Left Content */}
          <motion.div
            initial={{ opacity: 0, x: -50 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
          >
            <span className="inline-block px-4 py-2 rounded-full bg-primary/10 text-primary text-sm font-medium mb-4">
              О сервисе
            </span>
            <h2 className="text-3xl sm:text-4xl md:text-5xl font-bold text-foreground mb-6">
              Почему выбирают <span className="text-gradient">нас</span>?
            </h2>
            <p className="text-lg text-muted-foreground mb-8 leading-relaxed">
              Современная платформа для работы с данными Единого государственного регистра Беларуси. 
              Мы предоставляем удобный доступ к информации о юридических лицах и индивидуальных предпринимателях.
            </p>
            
            <div className="space-y-4">
              {benefits.map((benefit, index) => (
                <motion.div
                  key={index}
                  initial={{ opacity: 0, x: -20 }}
                  whileInView={{ opacity: 1, x: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.4, delay: index * 0.1 }}
                  className="flex items-center gap-3"
                >
                  <CheckCircle2 className="w-5 h-5 text-primary flex-shrink-0" />
                  <span className="text-foreground">{benefit}</span>
                </motion.div>
              ))}
            </div>
          </motion.div>

          {/* Right Content - Stats Card */}
          <motion.div
            initial={{ opacity: 0, x: 50 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
            className="relative"
          >
            <div className="bg-card rounded-3xl p-8 sm:p-10 shadow-card border border-border">
              <div className="grid grid-cols-2 gap-8">
                <motion.div
                  className="text-center p-6 rounded-2xl bg-primary/5 hover:bg-primary/10 transition-all duration-300 shadow-soft hover:shadow-glow glass"
                  whileHover={{ scale: 1.05 }}
                  transition={{ duration: 0.2 }}
                >
                  <div className="text-4xl sm:text-5xl font-bold text-gradient mb-2">500K+</div>
                  <div className="text-muted-foreground">Компаний в базе</div>
                </motion.div>
                <motion.div
                  className="text-center p-6 rounded-2xl bg-accent/5 hover:bg-accent/10 transition-all duration-300 shadow-soft hover:shadow-glow glass"
                  whileHover={{ scale: 1.05 }}
                  transition={{ duration: 0.2 }}
                >
                  <div className="text-4xl sm:text-5xl font-bold text-gradient mb-2">20+</div>
                  <div className="text-muted-foreground">Справочников</div>
                </motion.div>
                <motion.div
                  className="text-center p-6 rounded-2xl bg-accent/5 hover:bg-accent/10 transition-all duration-300 shadow-soft hover:shadow-glow glass"
                  whileHover={{ scale: 1.05 }}
                  transition={{ duration: 0.2 }}
                >
                  <div className="text-4xl sm:text-5xl font-bold text-gradient mb-2">99.9%</div>
                  <div className="text-muted-foreground">Uptime</div>
                </motion.div>
                <motion.div
                  className="text-center p-6 rounded-2xl bg-primary/5 hover:bg-primary/10 transition-all duration-300 shadow-soft hover:shadow-glow glass"
                  whileHover={{ scale: 1.05 }}
                  transition={{ duration: 0.2 }}
                >
                  <div className="text-4xl sm:text-5xl font-bold text-gradient mb-2">&lt;100ms</div>
                  <div className="text-muted-foreground">Время ответа</div>
                </motion.div>
              </div>
            </div>

            {/* Decorative Elements */}
            <div className="absolute -z-10 -top-4 -right-4 w-full h-full bg-primary/10 rounded-3xl" />
          </motion.div>
        </div>
      </div>
    </section>
  );
};
