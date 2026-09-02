ldap_code = """
% We need language for the applies predicate that is not related to any other predicate.
#pred blawx_applies(Y,X) :: '@(Y) applies to @(X)'.
#pred holds(user,blawx_applies,Y,Z) :: 'it is provided as a fact that @(Y) applies to @(Z)'.
#pred holds(user,-blawx_applies,Y,Z) :: 'it is provided as a fact that it is not the case that @(Y) applies to @(Z)'.
#pred holds(X,blawx_applies,Y,Z) :: 'the conclusion in @(X) that @(Y) applies to @(Z) holds'.
#pred holds(X,-blawx_applies,Y,Z) :: 'the conclusion in @(X) that it is not the case that @(Y) applies to @(Z) holds'.
#pred according_to(X,blawx_applies,Y,Z) :: 'according to @(X) @(Y) applies to @(Z)'.
#pred according_to(X,-blawx_applies,Y,Z) :: 'according to @(X) it is not the case that @(Y) applies to @(Z)'.
#pred defeated(X,blawx_applies,Y,Z) :: 'the conclusion in @(X) that @(Y) applies to @(Z) is defeated'.
#pred defeated(X,-blawx_applies,Y,Z) :: 'the conclusion in @(X) that it is not the case that @(Y) applies to @(Z) is defeated'.

% Consume the facts a Holds block generates for blawx_applies.
%
% Every ordinary predicate gets this bridge from the third clause of its
% attributed rule -- scasp_generator.js emits `L(X) :- holds(S,L,X).` next to
% each `according_to`/`holds` pair -- but blawx_applies is built in here rather
% than declared in a workspace, so no attributed rule ever concludes it and no
% such bridge is ever generated for it. Without the clause below, a Holds block
% naming blawx_applies is silently inert: the fact is asserted into the program
% and nothing can read it.
%
% Only the negative direction is bridged. Applicability is default-true: a
% section is made subject to it by the closed-world idiom
% `blawx_applies(S,A) :- not -blawx_applies(S,A).` (bird's sec_5 workspace
% writes exactly that), so wherever that default is present the positive twin
% `blawx_applies(S,X) :- holds(_Z,blawx_applies,S,X).` concludes only what the
% default already concludes. Adding it would buy nothing and would let a
% document that asserts both polarities derive blawx_applies and
% -blawx_applies at once, which costs it every stable model it had.
-blawx_applies(S,X) :- holds(_Z,-blawx_applies,S,X).
"""