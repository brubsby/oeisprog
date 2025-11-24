This page describes my philosophy on programs in the OEIS.

== Types of programs ==
What kinds of programs should be added to the OEIS, and how?

Generally, sequences are improved by adding programs. They can serve many purposes:
* explaining the sequence unambiguously
* describing computational 'tricks'
* computing things directly:
** isolated terms like a(n)
** the first n terms
** all terms up to some limit
** whether a number is an element of the sequence
** the successor (predecessor) of a sequence member

I feel that all of these can be useful, though the particular choices will be determined by the specifics of the sequence. Though some of these forms allow others to be defined, I don't think it's generally useful to define these by these relations (but rather only when there is a more efficient technique). Suppose a monotonically increasing sequence of positive integers (with offset 1) has a function <code>is(n)</code> which tests for membership in the sequence. A function giving the n-th term can be defined thus:
: <code>a(n)=my(k=0); while(n > 0, k=k+1; if(is(k), n=n-1)); return(k)</code>
<!-- This code is more idiomatic, but the code above is designed to be more easily read by those not familiar with GP.
: <code>a(n)=my(k); while(n, if(is(k++), n--)); k</code>
-->
but this gives no additional information beyond that stored in the function <code>is(n)</code>. Other programs can be simulated in like fashion.

== Naming conventions ==

I recommend the following conventions for naming programs.

* <code>a(n)</code> for a program which computes the ''n''-th term of the sequence. Offset should be respected.
* <code>is(n)</code> for a program which tests whether ''n'' is a member of the sequence or not. This generally only makes sense in sequences which represent sets (usually as a strictly increasing sequence). Mathematica programs (only) may instead choose a name of the form <code>PropertyQ[n_]</code> where "Property" is a brief description of the sequence, e.g., Squarefree.
* <code>list(lim)</code> for a program which lists the terms of the sequence up to ''lim''. This isn't needed when there is already code for <code>is(n)</code> unless the program is more efficient than running <code>is</code> over each number in the range. Like <code>is(n)</code>, this generally only makes sense for set-like sequences.
* <code>first(n)</code> for a program which lists the initial terms of the sequence up to index ''n''. This isn't needed when there is already code for <code>a(n)</code> unless the program is more efficient than running <code>a</code> over the indices up to ''n''. For example, if computing the ''n''-th term requires finding the first ''n'' terms, you might as well return them with <code>first(n)</code> rather than throw all but the last away to make <code>a(n)</code>.

Sometimes the above are not practical. Here are more specialized or last-ditch types.
* <code>row(n)</code> for a program which returns an array corresponding to the ''n''-th row of the sequence. This should only be used for {{OEIS|keyword:tabl|tabl}} or {{OEIS|keyword:tabf|tabf}} sequences.
* <code>do(x)</code> for a program which lists the initial terms of the sequence. Larger values of ''x'' should not decrease the number of terms returned, and there should be some ''x'' which will generate the first ''n'' terms for any ''n''. (This is useful when there is no obvious way to write <code>first(n)</code> or <code>list(lim)</code>, or if this would cause needless inefficiency.)
* <code>step(k)</code> for a program which returns a(n+1) when given a(n).
* <code>step(k,n)</code> for a program which returns a(n+1) when given a(n) and n.
* <code>has(n)</code> for a program which checks if n has a property required for n to be in the sequence. If n is in the sequence, <code>has(n)</code> must return <code>true</code> (however this is represented in the language); otherwise it may return <code>true</code> or <code>false</code>. Since this does not specify the sequence it should only be used as part of a larger collection of functions.

== Comments ==
Generally, programs in the OEIS do not need comments beyond marking authorship. Substantial comments should be written elsewhere: in the comments section, the formula section, etc. Occasionally there are relevant points to be raised about a program but which do not make sense in the broader context of the sequence; in that case comments are appropriate.

== Input validation ==
Scripts in the OEIS should generally be brief. Input validation is not required: if a term outside the domain is requested, the result is undefined behavior.

In particular, scripts like

: <code>a(n)=if(n<0, return(0)); n^2</code>

are not recommended (assuming the offset is 0, in this case); instead write

: <code>a(n)=n^2</code>

Communicating succinctly is more important than handling erroneous input, and in any case returning 0 is not useful. In fact, there is often a useful interpretation of the values of a sequence before its offset, and this script gives the natural extension. (See also [[Doubly infinite sequences]] and [[Index to OEIS: Section Tu #2wis|its Index entry]].)

In some cases it may be important to catch invalid input. (This is more common with full programs uploaded to the OEIS and listed under the links section.) In those cases, you should throw an error (or at least a warning) in the manner appropriate to your language. ''It is actively harmful'' to return a 0 in such cases; if it is important to find invalid input, you should not hide this with potentially-valid output like 0 or -1 but rather alert the user. So

:<code>m >= 0 || alert('Input ' + m + ' is invalid!');</code>

or

:<code>if(type(x) != "t_INT", error("x must be an integer: "x))</code>

or

:<code>if (n instanceof Integer == false)</code>
::<code>throw new Exception("n cannot be interpreted as an integer: " + n)</code>

or even

:<code>if (n < 0) exit(EXIT_FAILURE);</code>

See also the [http://www.open-std.org/jtc1/sc22/wg14/www/docs/n1124.pdf C standard] (3.4.3, undefined behavior) and the [http://pari.math.u-bordeaux.fr/pub/pari/manuals/2.10.0/users.pdf PARI User's Manual] (1.4, The PARI philosophy).

== Format ==
Readability is important. Programs should be kept to a minimum reasonable size (but please don't {{Wikipedia|Code golf|golf}}).

Sometimes a sequence is very hard to compute, or computing it efficiently is of great importance. In these cases full programs may be required, more than will reasonably fit in the Programs section. In that case the program should be uploaded and displayed in the Links section, with a pointer under Programs, e.g.:
: (Perl) See Smith link.
In this case the normal restrictions on comments do not apply, indeed, comments are recommended in full programs. Likewise, checking inputs for validity is often a good idea and even unit tests might be reasonable in full programs.

