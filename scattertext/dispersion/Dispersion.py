from typing import Optional, Callable, List

import numpy as np
import pandas as pd
from scattertext.termranking import AbsoluteFrequencyRanker
from scipy.sparse import csc_matrix, csr_matrix
from sklearn.preprocessing import StandardScaler

from scattertext.smoothing.lowess import Lowess
from scattertext.termranking.TermRanker import TermRanker
from scattertext.TermDocMatrix import TermDocMatrix


class Dispersion(object):
    def __init__(
            self,
            corpus=None,
            term_doc_mat=None,
            non_text=False,
            use_categories=False,
            tqdm=None,
            regressor=None,
            term_ranker: Optional[TermRanker]=None,
    ):
        """
        From https://www.researchgate.net/publication/332120488_Analyzing_dispersion
        Stefan Th. Gries. Analyzing dispersion. April 2019. Practical handbook of corpus linguistics. Springer.

        Parts are considered documents, unless use_categories is True. Then categories are treated as parts.

        Term ranker is acttive is use_categories is True
        """

        '''
        following Gries' notation, for the following example:
        b a m n i b e u p
        b a s a t b e w q n
        b c a g a b e s t a
        b a g h a b e a a t
        b a h a a b e a x a t

        (1) l = 50 (the length of the corpus in words)
        (2) n = 5 (the length of the corpus in parts)
        (3) s = (0.18, 0.2, 0.2, 0.2, 0.22) (the percentages of the n corpus part sizes)
        (4) f = 15 (the overall frequency of a in the corpus)
        (5) v = (1, 2, 3, 4, 5) (the frequencies of a in each corpus part 1-n)
        (6) p = (1/9, 2/10, 3/10, 4/10, 5 /11) (the percentages a makes up of each corpus part 1-n)
        '''
        self.corpus = None
        self.use_metadata = non_text
        if corpus is None and term_doc_mat is None:
            raise Exception("Required non-None argument for corpus or term_doc_mat.")
        X = self.__get_X(corpus, non_text, term_doc_mat, term_ranker, use_categories)
        part_sizes = X.sum(axis=1)
        self.l = X.sum().sum()
        self.n = X.shape[0]
        self.f = X.sum(axis=0)
        self.v = X
        self.p = X.multiply(csc_matrix(1. / X.sum(axis=1)))
        self.s = part_sizes / self.l
        self.tqdm = tqdm
        self.regressor = Lowess() if regressor is None else regressor

    def __get_X(self, corpus, non_text, term_doc_mat, term_ranker, use_categories):
        if term_doc_mat is not None:
            return term_doc_mat
        if corpus is not None:
            self.corpus = corpus
            if use_categories is True:
                if term_ranker is None:
                    term_ranker = AbsoluteFrequencyRanker

                term_ranker = term_ranker(term_doc_matrix=corpus).set_non_text(non_text=non_text)
                return csr_matrix(term_ranker.get_ranks('').values.T)
                #return term_ranker.get_ranks('').values
            else:
                return corpus.get_term_doc_mat(non_text=non_text)
                # if non_text:
                # if use_categories is False:
                # X = corpus.get_metadata_doc_mat()
                # else:
                #    X = csr_matrix(corpus.get_metadata_freq_df().values.T)
                # else:
                # if use_categories is False:

                # else:
                # X = csr_matrix(corpus.get_term_freq_df().values.T)
        raise Exception()
    def dispersion_range(self):
        """
        range: number of parts containing a = 5
        """
        return (self.v > 0).sum(axis=0).A1

    def sd_population(self):
        return np.sqrt(StandardScaler(with_mean=False).fit(self.v).var_)

    def vc(self):
        """
        Direct quote from Gries (2019)
        A maybe more useful variant of this measure is its normalized version, the variation
        coefficient (vc, see (9)); the normalization consists of dividing sdpopulation by the mean frequency
        of the element in the corpus parts f/n:
        """
        ss = StandardScaler(with_mean=False).fit(self.v)
        return np.sqrt(ss.var_) / ss.mean_

    def jullands_d(self):
        """
        Direct quote from Gries (2019)

        The version of Juilland's D that can handle differently large corpus parts is then computed
        as shown in (10). In order to accommodate the different sizes of the corpus parts, however, the
        variation coefficient is not computed using the observed frequencies v1-n (i.e. 1, 2, 3, 4, 5 in files
        1 to 5 respectively, see (5) above) but using the percentages in p1-n (i.e. how much of each corpus
        part is made up by the element in question, i.e. 1/9, 2/10, 3/10, 4/10, 5/11, see (6) above), which is what
        corrects for differently large corpus parts:
        """
        ss = StandardScaler(with_mean=False).fit(self.p)
        return 1 - (np.sqrt(ss.var_) / ss.mean_) / np.sqrt(self.n - 1)

    def rosengrens(self):
        '''
        Direct quote from Gries (2019)

        The version of Rosengren’s S that can handle differently large corpus parts is
        shown in (12). Each corpus part size’s in percent (in s) is multiplied with the
        frequencies of the element in question in each corpus part (in v1-n); of each product,
        one takes the square root, and those are summed up, that sum is squared, and divided
        by the overall frequency of the element in question in the corpus (f)'''

        vs = self.v.multiply(self.s)
        return np.power(np.sqrt(vs).sum(axis=0).A1, 2) * 1. / self.get_frequency()

    def dp(self):
        '''
        Direct quote from Gries (2019)

        Finally, Gries (2008, 2010) and the follow-up by Lijffijt and Gries (2012)
        proposed a measure called DP (for deviation of proportions), which falls between
        1-min s (for an extremely even distribution) and 1 (for an extremely clumpy
        distribution) as well as a normalized version of DP, DPnorm, which falls between 0
        and 1, which are computed as shown in (13). For DP, one computes the differences
        between how much of the element in question is in each corpus file in percent on the
        one hand and the sizes of the corpus parts in percent on the other – i.e. the differences
        between observed and expected percentages. Then, one adds up the absolute values
        of those and multiplies by 0.5; the normalization then consists of dividing this values
        by the theoretically maximum value of DP given the number of corpus parts (in a
        way reminiscent of (11)'''
        return np.sum(np.abs(self.v.multiply(1. / self.get_frequency()) - self.s),
                      axis=0).A1 / 2

    def dp_norm(self):
        return self.dp() / (1 - self.s.min())

    def kl_divergence(self):
        '''
        Direct quote from Gries (2019)
        The final measure to be discussed here is one that, as far as I can tell, has never
        been proposed as a measure of dispersion, but seems to me to be ideally suited to be
        one, namely the Kullback-Leibler (or KL-) divergence, a non-symmetric measure
        that quantifies how different one probability distribution (e.g., the distribution of
        all the occurrences of a across all corpus parts, i.e. v/f) is from another (e.g., the
        corpus part sizes s); the KL-divergence is computed as shown in (14) (with log2s of 167
        0 defined as 0):'''
        vf = self.v.multiply(1. / self.f)
        vfs = vf.multiply(1. / self.s)
        vfs.data = np.log(vfs.data) / np.log(2)
        return np.sum(vf.multiply(vfs), axis=0).A1

    def da(self):
        '''
        Metric from Burch (2017).

        Brent Burch, Jesse Egbertb and Douglas Biber. Measuring Lexical Dispersion in Corpus Linguistics. JRDS. 2016.
        Article: https://journal.equinoxpub.com/JRDS/article/view/9480

        D_A = 1 - ((n * (n - 1))/2) * sum_{i in 0, n - 1} sum{j in i + 1, n} |v_i - v_j|/(2*mean(v))

        :return:
        '''
        n = self.n

        constant = 1. / (n * (n - 1) / 2)

        it = range(self.v.shape[1])
        if self.tqdm is not None:
            it = self.tqdm(it)

        da = []
        for word_i in it:
            v_word_id = self.v.T[word_i]
            if type(v_word_id) != np.ndarray:
                y = v_word_id.todense().A1
            else:
                y = v_word_id
            yt = np.tile(y, (n, 1))
            pairs_sum = np.sum(np.abs(yt - yt.T)) / 2
            da_score = 1 - pairs_sum * constant / (2 * y.mean())
            da.append(da_score)

        da_vec = np.array(da)
        da_vec[da_vec < 0] = 0  # correct for floating point issues
        return da_vec

    def get_df(self, terms=None, include_da=False):
        if terms is None and self.corpus is not None:
            terms = self.get_names()

        freq = self.get_frequency()
        df_content = {
            'Frequency': freq,
            'Range': self.dispersion_range(),
            'SD': self.sd_population(),
            'VC': self.vc(),
            "Juilland's D": self.jullands_d(),
            "Rosengren's S": self.rosengrens(),
            'DP': self.dp(),
            'DP norm': self.dp_norm(),
            'KL-divergence': self.kl_divergence(),
        }
        if include_da:
            df_content['DA'] = self.da()
        if terms is None:
            df = pd.DataFrame(df_content)
        else:
            df = pd.DataFrame(df_content, index=terms)
        return df

    def get_names(self):
        return self.corpus.get_metadata() if self.use_metadata else self.corpus.get_terms()

    def get_adjusted_metric(self, metric=None, freq=None):
        '''
        Returns the difference between DA and the Lowess estimate of DP from frequency

        :param metiric: Optional[np.array], metric to analyze, defaults to DP

        :param freq: Optional[np.array], Word frequencies
        :return: np.array, frequency-adjusted metric
        '''
        if metric is None:
            observed = self.dp()
        elif metric == 'DA':
            observed = self.da()
        else:
            observed = self.get_df()[metric]

        if freq is None:
            freq = self.get_frequency()
        freq_est_metric = self.__fit_predict(freq, metric)
        return observed - freq_est_metric

    def get_adjusted_metric_df(self, metric=None, freq=None):
        '''
        Returns the difference between the metric and the Lowess estimate of metric from frequency

        :param metiric: Optional[np.array], metric to analyze, defaults to DP

        :param freq: Optional[np.array], Word frequencies
        :return: np.array, frequency-adjusted metric
        '''
        if metric is None:
            metric = self.dp()
        elif metric == 'DA':
            metric = self.da()
        else:
            metric = self.get_df()[metric]

        if freq is None:
            freq = self.get_frequency()
        freq_est_metric = self.__fit_predict(freq, metric)
        adjusted_metric = metric - freq_est_metric
        return pd.DataFrame({
            'Frequency': freq,
            'Metric': metric,
            'Estimate': freq_est_metric,
            'Residual': adjusted_metric
        }, index=self.get_names())

    def __fit_predict(self, freq: np.array, metric: np.array) -> np.array:
        regressor = self.regressor.fit(freq.reshape(-1, 1), metric)
        pred = regressor.predict(freq.reshape(-1, 1))
        freq_est_metric = pred.T[0]
        return freq_est_metric

    def get_frequency(self):
        if len(self.f.shape) == 1:
            return self.f
        return self.f.A1


def get_category_dispersion(
        corpus: TermDocMatrix,
        metric: str,
        corpus_to_parts: Optional[Callable[['TermDocMatrix'], List]] = None,
        non_text: bool = False
) -> pd.DataFrame:
    """

    :param corpus:  TermDocMatrix to process
    :param metric: a metric present in Dispersion.get_df. May be DA.
    :param corpus_to_parts: Optional function which takes a TermDocMatrix and returns a list of parts of each doc. None indicates each doc is a separate part.
    :param non_text: Use non text features. False by default
    :return: Dataframe giving category-specific features
    """
    data = {}
    for category in corpus.get_categories():
        category_corpus = corpus.remove_categories([c for c in corpus.get_categories() if c != category])
        if corpus_to_parts is not None:
            category_corpus = category_corpus.recategorize(corpus_to_parts)
        dispersion_df = Dispersion(
            category_corpus,
            non_text=non_text,
            use_categories=corpus_to_parts is not None,
        ).get_df(include_da=metric == 'DA')
        data[category + '_Frequency'] = dispersion_df.Frequency
        data[category + '_' + metric] = dispersion_df[metric]
    return pd.DataFrame(data).fillna(0)
