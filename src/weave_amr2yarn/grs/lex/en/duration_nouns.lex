% Nouns that name a stretch of time, matched on the anchored lemma.
%
% The aspect package uses this to tell a temporal adverbial from any
% other one: what makes "in three hours" temporal is the head noun, not the
% preposition.
%
% Every entry is attested under one of the three
% sibling temporal synsets below (all hyponyms of measure.n.02).  This is a
% curated subset of common metric duration nouns, NOT the full hyponym
% closure — the full closure (~1000 lemmas) over-generates named/geological
% periods ("Renaissance", "Jurassic", seasons) that are not container-
% adverbial duration units.  Verified with nltk.corpus.wordnet.
%   time_period.n.01   "an amount of time"  -> all but `interval`
%   time_unit.n.01     "a unit for measuring time periods"  -> second..month
%   time_interval.n.01 "a definite length of time marked off by two instants"
%                                            -> `interval`
%
% Column: duration_noun (UD anchor lemma)
%
duration_noun
second
minute
hour
day
week
fortnight
month
year
decade
century
millennium
while
spell
interval
stretch
span
lifetime
time
