#ifndef BOOTCHART_MACRO_H
#define BOOTCHART_MACRO_H

/* These macros give the information about branch prediction to
 * gcc compiler. 
 */

#if __GNUC__ > 3 || __GNUC__ == 3
#define likely(x)			(__builtin_expect(!!(x),1))
#define unlikely(x)			(__builtin_expect(!!(x),0))
#else
#define likely(x)			(x)
#define unlikely(x)			(x)
#endif /* __GNUC__ */

#endif /* BOOTCHART_MACRO_H */
