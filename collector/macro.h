#ifndef BOOTCHART_MACRO_H
#define BOOTCHART_MACRO_H

#include <assert.h>

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

/* In order to easy debug, override glibc assert() and define log()
 * function
 */
#undef assert
#define PREFIX				"[bootchart] "
#ifdef CONFIG_DEBUG
#include <stdlib.h>
#define log_debug(fmt,...)		fprintf(stderr, PREFIX "%s:%d " fmt, __FILE__, __LINE__, ##__VA_ARGS__)
#define assert_debug(expr)				\
	do {						\
		if (unlikely(!(expr))){			\
			log_debug("Assertion failed");	\
			abort();			\
		}					\
	} while(0)
#define log			log_debug
#define assert(expr)		assert_debug(expr)
#else
#define log(fmt,...)		fprintf(stderr, PREFIX fmt, ##__VA_ARGS__)
#define assert(expr)		do {} while(0)
#endif /* CONFIG_DEBUG */

#endif /* BOOTCHART_MACRO_H */
