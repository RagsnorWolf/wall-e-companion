import { motion } from "framer-motion";

export function Panel({
  title,
  code,
  icon: Icon,
  actions,
  children,
  className = "",
  bodyClassName = "",
  delay = 0,
}) {
  return (
    <motion.section
      className={`panel ${className}`}
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      <header className="panel__head">
        <div className="panel__title">
          <span className="panel__tick" aria-hidden="true" />
          {Icon ? <Icon size={14} className="panel__icon" /> : null}
          <span>{title}</span>
          {code ? <span className="panel__code">{code}</span> : null}
        </div>
        {actions ? <div className="panel__actions">{actions}</div> : null}
      </header>
      <div className={`panel__body ${bodyClassName}`}>{children}</div>
    </motion.section>
  );
}

export function CornerBrackets() {
  return (
    <>
      <span className="corner corner--tl" aria-hidden="true" />
      <span className="corner corner--tr" aria-hidden="true" />
      <span className="corner corner--bl" aria-hidden="true" />
      <span className="corner corner--br" aria-hidden="true" />
    </>
  );
}
